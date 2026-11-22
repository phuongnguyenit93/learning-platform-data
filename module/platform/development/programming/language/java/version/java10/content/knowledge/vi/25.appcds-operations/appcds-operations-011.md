# Quyền truy cập và tính toàn vẹn của kho chia sẻ AppCDS

*Chủ đề cha: Vận hành AppCDS — Java 10. Bài này tập trung vào bảo vệ **shared archive (kho dữ liệu lớp, thường là tệp `.jsa`)** của Class Data Sharing (CDS) / Application Class-Data Sharing (AppCDS): ai được tạo, đọc, sửa hoặc thay thế kho; cơ chế kiểm tra tính toàn vẹn nào có sẵn; cách triển khai bất biến, xác minh và khôi phục khi archive không sử dụng được. Nội dung chỉ sử dụng kiến thức còn áp dụng trong Java hiện đại. Ví dụ chạy trên JDK 17 trở lên với HotSpot có hỗ trợ CDS.*

## 1. Tại sao archive cần được bảo vệ?

AppCDS giúp JVM lưu những dữ liệu class đã được chuẩn bị vào **CDS archive** để các lần chạy tiếp theo có thể nạp nhanh hơn. Với những trang metadata ở chế độ chỉ đọc, nhiều JVM tương thích trên cùng host có thể memory-map cùng dữ liệu, giúp giảm trùng lặp bộ nhớ và thời gian xử lý class. Java 10 giới thiệu khả năng đưa application class vào archive qua JEP 310; các phiên bản JDK sau tiếp tục phát triển quy trình tạo và sử dụng archive.

Đổi lại, archive trở thành một **artifact đầu vào của JVM**. Mỗi tiến trình khởi động có thể đọc tệp này **rất sớm**, trước khi code `main` của ứng dụng thực hiện những bước kiểm tra tùy biến. Nếu đường dẫn archive bị kẻ không có quyền thay thế, archive hỏng trong lúc phân phối hoặc runtime không khớp phiên bản JDK/JAR, việc khởi động có thể thất bại hoặc JVM có thể bỏ qua tối ưu CDS tùy cấu hình.

Do đó, cần quản lý hai tính chất khác nhau:

1. **Quyền truy cập (access control):** chỉ các chủ thể tin cậy được tạo, ghi đè, xóa hoặc thay thế archive và các thư mục chứa nó; JVM production được quyền đọc đúng artifact.
2. **Tính toàn vẹn (integrity):** archive không thay đổi trái phép hoặc vô ý so với bản đã tạo/kiểm duyệt; nếu thay đổi hoặc không tương thích thì quy trình phải phát hiện và xử lý.

**Điểm tối quan trọng:** các trang **read-only** được JVM ánh xạ **không đồng nghĩa** tệp `.jsa` trên đĩa đã được bảo vệ khỏi ghi đè. Read-only memory mapping là cơ chế bảo vệ vùng nhớ của process; phân quyền file và thư mục là trách nhiệm của hệ điều hành, build/deployment và người vận hành.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chính xác archive `.jsa` là dữ liệu đã chuẩn bị cho JVM, không phải một Java heap chung.
2. Phân biệt bảo vệ **trang nhớ đã map** với bảo vệ **tệp archive và đường dẫn đến tệp**.
3. Thiết kế quyền cho ba vai trò: tài khoản build, tài khoản triển khai và tài khoản chạy ứng dụng.
4. Hiểu vai trò của permission/ACL, quyền trên thư mục cha, symlink, đổi tên và TOCTOU.
5. Sử dụng `-XX:+VerifySharedSpaces` để phát hiện một số lỗi hỏng archive bằng CRC32.
6. Phân biệt CRC32 (kiểm tra hỏng ngẫu nhiên), SHA-256 (digest mật mã) và **xác thực nguồn** bằng chữ ký hoặc manifest từ kênh đáng tin.
7. Tạo và sử dụng dynamic archive trên JDK 17+, xác nhận application class thật sự load từ `shared objects file`.
8. Kiểm thử một archive chỉ đọc và hiểu vì sao archive nên bất biến ở production.
9. Biết cách xử lý archive không tương thích do JDK/JAR/classpath thay đổi mà không mặc định kết luận đã có tấn công.
10. Thiết kế phát hành theo phiên bản, stage–verify–publish, rollout/rollback và giám sát lỗi CDS.
11. Chọn hành vi fail-open tối ưu hóa (chạy không có AppCDS) hay fail-fast theo hợp đồng sản phẩm; không dùng `-Xshare:on` làm mặc định production chỉ để thử archive.
12. Tránh những bài kiểm thử gây mất dữ liệu bằng cách chỉ thử trên file tạm/bản sao archive.

## 3. “Kho chia sẻ” chính xác là gì?

Một file AppCDS `app.jsa` lưu một số thông tin về class mà HotSpot có thể tái sử dụng. Tệp này có dạng **nội bộ của JVM**, không phải định dạng dữ liệu nghiệp vụ chung, không phải JAR thông thường và không phải một kho object/JSON mà ứng dụng tự ý cập nhật.

```text
       Build / training process (được phép tạo archive)
                         |
                         v
              app.jar + JDK phù hợp
                         |
                         v
                 app.jsa đã kiểm tra
                         |
                    [publish]
                         |
          +--------------+--------------+
          |                             |
      JVM production A              JVM production B
     đọc app.jsa (RO)              đọc app.jsa (RO)
     dữ liệu lớp phù hợp           dữ liệu lớp phù hợp
     heap/threads riêng            heap/threads riêng
```

Sơ đồ chỉ thể hiện quan hệ tin cậy và cách sử dụng; các JVM cần tương thích với archive, classpath/JAR và điều kiện runtime. Tính năng chia sẻ chỉ đọc không biến `static` field, stack, Java heap hay đối tượng business thành dữ liệu chung.

### 3.1. Default archive và application archive

- **Default CDS archive:** nhiều bản phân phối JDK hiện đại đã kèm archive cho các core classes. Thường nằm trong thư mục cài JDK. Quản lý quyền của nó cùng runtime image/JDK, không tự chỉnh sửa nó từ account ứng dụng.
- **Application archive:** archive bổ sung do build/CI/deployment tạo cho những class ứng dụng đủ điều kiện; có thể là **dynamic** hoặc **static** archive. Nó cũng cần bảo vệ như một artifact của release.
- **Dynamic archive:** có thể được tạo bằng `-XX:ArchiveClassesAtExit=app.jsa` khi JVM kết thúc, dựa trên base archive phù hợp. Đây là workflow hữu ích trên JDK 17+.
- **Static archive:** có thể được tạo bằng class list và `-Xshare:dump`; quyền lưu trữ và kiểm chứng cũng cần được thực hiện tương tự.

**Không đưa các hướng dẫn yêu cầu cờ `-XX:+UseAppCDS` của các bản thương mại/cơ chế lịch sử làm mặc định cho JDK 17+.** Các ví dụ dưới đây dùng tùy chọn đang được tài liệu Java SE 17 hỗ trợ.

## 4. Hai lớp bảo vệ phải được phân biệt

| Lớp bảo vệ | Ví dụ | Nó bảo vệ điều gì? | Nó không bảo vệ điều gì? |
| --- | --- | --- | --- |
| OS memory mapping | Trang metadata archive ở chế độ read-only | Process không sửa trực tiếp các trang mapped read-only ấy | Không tự chặn người có quyền thay đổi tệp trên đĩa |
| Quyền file/ACL | Runtime user chỉ có quyền đọc `app.jsa` | Hạn chế ghi/xóa từ chủ thể không được cấp quyền | Nếu thư mục cha cho thay tên tệp, bảo vệ file riêng lẻ có thể chưa đủ |
| Quyền thư mục | Chỉ trusted deployer được tạo/xóa/đổi tên trong release dir | Ngăn thay file bằng một file khác tại cùng path | Không xác thực nội dung artifact nếu nguồn build đã bị xâm nhập |
| Kiểm tra CRC của HotSpot | `-XX:+VerifySharedSpaces` | Phát hiện hỏng dữ liệu vô ý dựa trên CRC32 | Không phải chữ ký mật mã; không chứng minh publisher là ai |
| SHA-256 từ trusted manifest | Hash archive khớp digest đã được phê duyệt | Phát hiện nội dung khác với bản đã định danh | Hash tự tính và tự tin không chứng minh nguồn phát hành |
| Chữ ký số/nguồn artifacts tin cậy | Signed manifest, image digest, registry policy | Chứng minh artifact thuộc release đã được chấp nhận khi xác minh khóa/chính sách | Không tự giải quyết vấn đề quyền runtime, JDK/JAR tương thích và race |
| Kiểm tra tính tương thích CDS | Log `cds`/`class+load` | Cho biết JVM có nạp archive và class hay không | Không phải cơ chế xác thực mật mã |

**Một hệ thống an toàn cần kết hợp**, không chỉ bật một JVM flag hoặc đánh dấu file là read-only.

## 5. Mô hình quyền theo vai trò

Đặt ba vai trò rõ ràng:

| Vai trò | Cần quyền | Không cần hoặc không nên có |
| --- | --- | --- |
| **Build/training job** | Đọc JDK, classpath/JAR được phép; tạo archive ở vùng build riêng | Sửa ngẫu nhiên archive đã phát hành của production |
| **Trusted deployer/release job** | Đọc và kiểm chứng artifacts; đưa archive vào thư mục release; quản lý đổi phiên bản | Chạy business traffic với quyền build/administrator |
| **Runtime process** | Đọc đúng JDK, JAR, archive và traverse các thư mục liên quan | Tự ghi đè, đổi tên, xóa `.jsa` hoặc sửa nội dung thư mục release |

Một mô hình thường gặp là:

- CI tạo `app.jar` và `app.jsa` bằng runtime version đã chọn.
- CI hoặc release pipeline lưu digest, provenance và thông tin JDK/JAR vào manifest của bản build.
- Trusted deployer tải artifact từ nguồn đã xác minh, stage và kiểm tra toàn vẹn.
- Deployer xuất bản vào một thư mục release bất biến.
- User của service Java chỉ được **đọc** archive, JAR và runtime image; không có quyền sửa thư mục chứa chúng.

### 5.1. Quyền đọc khác quyền ghi

JVM cần **đọc và ánh xạ** archive khi chạy. Trong môi trường bình thường, nó không cần quyền sửa `app.jsa` khi sử dụng qua `-XX:SharedArchiveFile`. Nếu application user vẫn có quyền ghi vào archive, một lỗ hổng trong business process có thể trở thành khả năng phá hỏng artifact mà các process Java khác cùng sử dụng.

Ngược lại, **tài khoản tạo archive** bằng `ArchiveClassesAtExit` cần quyền ghi trong thư mục output ở giai đoạn training. Vì vậy nên **tạo archive trước khi cấp quyền read-only cho runtime**. Không cố tạo archive mới ngay trong thư mục release bất biến bằng account chỉ có quyền đọc.

### 5.2. Đường dẫn cha quan trọng như quyền của file

Trên POSIX, muốn đọc một file trong thư mục, process thường phải có quyền **traverse** (`x`) với các thư mục cha và quyền đọc (`r`) với file. Quyền tạo/xóa/đổi tên mục trong thư mục chủ yếu do **quyền thư mục** kiểm soát, không chỉ do bit read-only trên chính file.

Ví dụ, chỉ `chmod 0444 app.jsa` trong thư mục mà user không tin cậy có thể đổi tên/xóa file thì chưa bảo vệ được việc thay thế nội dung nhìn qua path `app.jsa`. Windows cũng có các quyền trên thư mục và tệp thông qua ACL, không chỉ thuộc tính “Read-only” hiển thị trong Explorer.

**Bảo vệ cả cây đường dẫn**, đặc biệt thư mục release, bản JDK, JAR và archive. Đừng chỉ sửa permission trên file cuối cùng rồi coi đã xong.

## 6. Ví dụ quyền trên Linux: quyền tối thiểu thay vì một lệnh chmod đơn lẻ

Giả sử release pipeline đã tạo một thư mục `release-317` chứa `app.jar` và `app.jsa`, và có tài khoản/nhóm được thiết kế riêng.

Một ví dụ quyền cơ bản trong thư mục thử nghiệm do bạn sở hữu:

```bash
# Chỉ thao tác trên release-317 do chính bạn tạo.
chmod 0750 release-317
chmod 0440 release-317/app.jsa
chmod 0440 release-317/app.jar

# Kiểm tra permission và owner/group hiện tại.
stat -c '%a %U %G %n' release-317
stat -c '%a %U %G %n' release-317/app.jsa
namei -l release-317/app.jsa
```

Lệnh này **không tự chọn owner/group tin cậy**; trong production cần bộ phận vận hành đặt ownership/ACL phù hợp, thường tách identity deployer khỏi identity runtime. `0440` cho phép owner và group đọc, không cấp bit ghi cho file; `0750` cho phép owner quản lý thư mục và group traverse/read. Nếu runtime user không thuộc group phù hợp, nó sẽ không thể đọc file.

Các lưu ý:

- Không yêu cầu production runtime chạy bằng `root` chỉ để đọc archive.
- Không đưa thư mục chứa archive vào một đường dẫn mà tất cả local users có quyền ghi.
- Không dùng `chmod 777` để “chữa” lỗi permission của AppCDS.
- Không đặt archive tại một thư mục upload do người dùng cuối quản lý.
- Không giả định file mode phù hợp với Windows hoặc mọi hệ thống file mạng: dùng ACL tương ứng nền tảng.
- Các công cụ trên là **ví dụ POSIX**; Windows PowerShell/ACL cần quy trình khác.

**Chú ý:** người sở hữu file hoặc quản trị viên có thể thay đổi quyền theo chính sách OS; read-only bit không phải rào cản tuyệt đối chống lại admin hay tài khoản đã bị xâm nhập.

## 7. Ví dụ quan sát quyền trên Windows

PowerShell cho phép đọc các thuộc tính bề mặt và ACL của archive:

```powershell
Get-Item .\app.jsa | Select-Object Name, Length, IsReadOnly
Get-Acl .\app.jsa | Format-List Owner, Access
Get-Acl . | Format-List Owner, Access
```

Các lệnh là ví dụ đọc-only, chạy trong thư mục chứa archive. `IsReadOnly=True` có thể là thông tin hữu ích, nhưng **không tự chứng minh ACL thật đã từ chối mọi quyền sửa, xóa hoặc thay thế file**. Cần xem identity chạy service, quyền trên thư mục cha, inherited ACL, quyền delete/rename và group membership.

Trong một lần thử trên Windows/JDK hiện đại, archive được tạo đã mang thuộc tính read-only. Dù vậy, **không phụ thuộc mọi vendor/JDK/OS luôn tạo .jsa với thuộc tính ấy**. Hãy kiểm chứng ACL của môi trường thực tế. Ngay cả khi read-only attribute đã có, deployment vẫn cần chính sách owner/write permissions rõ.

Nếu doanh nghiệp dùng Windows service account hoặc NTFS ACL, hãy để hệ thống triển khai cấu hình ACL theo nguyên tắc least privilege, không dán một lệnh `icacls /grant Everyone:F` chỉ để hết báo access denied.

## 8. Bảo vệ archive khỏi thay thế bằng đường dẫn khác

Một tình huống nguy hiểm:

1. Đội triển khai xác minh digest của `/srv/app/current/app.jsa`.
2. Thư mục `current` hoặc một thư mục cha bị user không tin cậy đổi symlink/entry.
3. JVM sau đó được khởi động với **cùng chuỗi path**, nhưng path đã trỏ sang artifact khác.

Đây là dạng **time-of-check to time-of-use (TOCTOU)**. Ngay cả khi một tệp từng đạt kiểm tra SHA-256, một thay đổi đường dẫn sau kiểm tra vẫn có thể khiến JVM mở tệp khác.

Biện pháp phù hợp:

- Không để account không tin cậy ghi/đổi symlink/đổi tên trong release root.
- Ưu tiên **đường dẫn release theo phiên bản và bất biến** thay vì cập nhật cùng file tại chỗ.
- Thực hiện xác minh, stage và publish trong vùng do trusted deployer quản lý.
- Nếu dùng symlink `current`, chỉ deployer tin cậy được thay symlink và phải kiểm soát thao tác rollout.
- Tránh đường dẫn lấy trực tiếp từ request hoặc cấu hình chưa được validate đưa vào `-XX:SharedArchiveFile`.
- Đảm bảo runtime image, JAR, classpath và archive trong cùng một release có quan hệ tương thích.

**Không dựa vào `Files.isReadable`, `Files.isWritable` hoặc một lần kiểm tra hash trong `main` làm bảo vệ đủ mạnh**, vì khi `main` chạy thì JVM có thể đã đọc archive. Xác minh artifact cần diễn ra **trước khi khởi động JVM** ở pipeline/wrapper đáng tin.

## 9. Tính toàn vẹn: những câu hỏi khác nhau

Khi nói archive “nguyên vẹn”, cần phân biệt:

1. **Không hỏng vật lý/vô ý:** bytes không bị thay đổi trong lúc lưu trữ hoặc truyền tải.
2. **Đúng bản đã phê duyệt:** bytes khớp artifact của release cụ thể.
3. **Đúng nguồn tin cậy:** artifact do pipeline/nhà phát hành được phép sản xuất, không phải file attacker tự tạo và tự tính hash.
4. **Tương thích với JVM/JAR:** runtime có thể hiểu archive và sử dụng class đã archived.

Một bài test chỉ kiểm tra CRC có thể giúp câu hỏi 1, nhưng **không tự trả lời 2, 3, 4**. Tương tự, kiểm tra SHA-256 từ một manifest có thể trả lời câu hỏi 2 nếu manifest đã được tin cậy, nhưng không thay thế câu hỏi 4.

### 9.1. CRC32: phát hiện hỏng không phải chữ ký

HotSpot cung cấp cờ:

```bash
java -XX:+VerifySharedSpaces -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveSecurityDemo
```

Theo tài liệu Oracle Java SE 17, `-XX:+VerifySharedSpaces` yêu cầu JVM xác minh archive bằng **CRC32 checksums** trước khi sử dụng. Mục tiêu của cờ là kiểm tra **hư hại vô ý trong truyền tải hoặc lưu trữ**.

CRC32 là **checksum**, không phải thuật toán chống giả mạo có khóa. Một attacker có quyền tạo/sửa archive có thể tạo hoặc thay đổi dữ liệu cùng checksum phù hợp; vì vậy **CRC32 không chứng minh tính xác thực của publisher**. Oracle cũng nhấn mạnh cần bảo đảm archive không thể bị sửa khi chưa được cho phép.

**Không quảng cáo `-XX:+VerifySharedSpaces` là “bật chữ ký số cho AppCDS”.** Nó là công cụ kiểm tra integrity có giới hạn rõ.

### 9.2. SHA-256: kiểm tra bytes với digest tin cậy

SHA-256 là một hàm băm mật mã được dùng để định danh bytes:

```text
SHA-256(bytes của app.jsa) = digest 256 bit (64 ký tự hex)
```

Nếu digest tính từ archive **khớp** digest được lấy từ **manifest/phần metadata đã xác thực ở một kênh tin cậy**, ta có bằng chứng mạnh hơn rằng bytes không khác bản được phê duyệt.

Nhưng **nếu tự tính hash của file rồi ngay lập tức tin chính hash đó**, bạn chỉ biết hash đã tính được, chưa có bằng chứng file là bản đáng tin. Nếu attacker sửa được cả `app.jsa` lẫn file `app.jsa.sha256`, một phép so khớp đơn thuần có thể vẫn báo đúng.

Để xác thực nguồn, dùng một hoặc nhiều lớp:

- signed release manifest / chữ ký số với public key hoặc trust policy đáng tin;
- artifact registry có identity/provenance và quyền publish chặt;
- container image digest từ kênh triển khai đã xác minh;
- kiểm tra artifact trước khi đưa vào thư mục release không thể sửa bởi runtime user.

Không tự sáng tạo thuật toán mã hóa cho archive; dùng công cụ ký/xác minh artifact đã được tổ chức phê duyệt.

## 10. Kiểm tra SHA-256 bằng công cụ hệ điều hành

Ví dụ trên Linux/macOS có công cụ tương ứng:

```bash
sha256sum app.jsa

# Nếu trusted release cung cấp file manifest kiểu sha256sum:
sha256sum --check app.jsa.sha256
```

`sha256sum` là công cụ GNU điển hình trên Linux; macOS có thể dùng `shasum -a 256` hoặc công cụ phù hợp. Dòng `--check` chỉ có ý nghĩa **đảm bảo artifact khớp manifest** nếu file manifest đến từ nguồn tin cậy và có định dạng hợp lệ. Đừng download archive và checksum từ một nguồn không tin cậy rồi coi việc chúng khớp là xác thực nguồn.

Trên Windows PowerShell:

```powershell
Get-FileHash -LiteralPath .\app.jsa -Algorithm SHA256
```

Output có cột `Algorithm`, `Hash` và `Path`; **hash thật khác theo nội dung archive**, phiên bản JDK, tập class và cách dump. Không đóng đinh một digest cố định cho mọi máy.

### 10.1. Kiểm tra digest cần diễn ra khi nào?

Một chuỗi hợp lý:

1. CI tạo archive từ runtime/JAR đã chốt và đưa vào kho artifact.
2. CI xuất manifest digest và ký/chứng thực manifest theo chính sách.
3. Deployer tải cả archive, JAR và manifest từ nguồn tin cậy.
4. Deployer **xác thực manifest**, rồi đối chiếu digest bytes của archive.
5. Deployer đưa bản đã xác minh vào release directory do account tin cậy quản lý.
6. Service JVM đọc archive từ path cố định trong release đó.
7. Khi cập nhật/rollback, chuyển sang một release khác đã kiểm chứng.

**Không bắt ứng dụng Java tự kiểm tra archive trong method `main` rồi coi đó là biện pháp bảo vệ trước khi JVM nạp archive**: thứ tự khởi động không bảo đảm như vậy.

## 11. Chương trình Java 17+: kiểm tra SHA-256 bằng streaming

Một công cụ Java nhỏ có thể tính digest mà không phải nạp toàn bộ `.jsa` vào heap. **Chạy công cụ này như bước preflight độc lập, trước khi chạy ứng dụng production**, không phải trong `main` của ứng dụng sẽ đọc archive.

Tạo **`ArchiveSha256.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class ArchiveSha256 {
    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            throw new IllegalArgumentException(
                    "usage: ArchiveSha256 <file> [trustedSHA256]");
        }

        var digest = MessageDigest.getInstance("SHA-256");

        try (var in = Files.newInputStream(Path.of(args[0]))) {
            var buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
        }

        var actual = digest.digest();
        System.out.println("sha256="
                + HexFormat.of().formatHex(actual));

        if (args.length == 2) {
            var expected = HexFormat.of().parseHex(args[1]);
            boolean match =
                    MessageDigest.isEqual(actual, expected);
            System.out.println("matchesTrustedDigest=" + match);
            if (!match) {
                System.exit(3);
            }
        }
    }
}
```

Biên dịch và chạy từ **một JVM không phải ứng dụng đang chuẩn bị được bảo vệ**:

```bash
javac --release 17 ArchiveSha256.java

# In digest để so với manifest bên ngoài:
java ArchiveSha256 app.jsa
```

Stdout có dạng:

```text
sha256=<64 chữ số hex của archive cụ thể>
```

Đây là **mô tả hình thức**, không phải output literal cố định: giá trị phụ thuộc bytes `app.jsa`. Nếu truyền đối số thứ hai là 64 ký tự hex **lấy từ trusted manifest**:

- Nếu khớp, chương trình in `matchesTrustedDigest=true` và thoát mã 0.
- Nếu không khớp, in `matchesTrustedDigest=false` và thoát mã 3.
- Nếu tên file sai hoặc không đọc được, có thể ném `IOException`.
- Nếu digest hex sai cú pháp, `HexFormat.parseHex` ném `IllegalArgumentException`.

Chương trình được kiểm thử với Java hiện đại, biên dịch ở mức Java 17: đối chiếu đúng digest thì trả mã 0, digest cố tình không khớp thì trả mã 3. `HexFormat` là API có từ Java 17, không phải tính năng bắt buộc của Java 10.

**Giới hạn bảo mật:** đây là **kiểm tra digest**, không phải kiểm tra chữ ký số hoặc chứng thực người phát hành. Phải bảo vệ nơi lấy digest tin cậy và đường dẫn artifact để tránh TOCTOU.

## 12. Ví dụ AppCDS chạy được trên Java 17+

Để kiểm tra archive ở tình huống thực, dùng ứng dụng nhỏ có hai class. Tạo **`ArchiveSecurityDemo.java`**:

```java
public final class ArchiveSecurityDemo {
    private static int processRuns;

    static final class Helper {
        static String message() {
            return "class metadata ready";
        }
    }

    public static void main(String[] args) {
        processRuns++;

        System.out.println("processRuns=" + processRuns);
        System.out.println("message=" + Helper.message());
    }
}
```

Biên dịch, tạo JAR:

```bash
mkdir classes
javac --release 17 -d classes ArchiveSecurityDemo.java
jar --create --file app.jar --main-class ArchiveSecurityDemo -C classes .
```

Đây là các lệnh thao tác trong **thư mục demo riêng**; bảo đảm `app.jar`/`classes` chưa chứa dữ liệu khác cần giữ. Ứng dụng dùng class ở trong JAR để mô phỏng workflow AppCDS có thể archive application classes.

Chạy bình thường:

```bash
java -cp app.jar ArchiveSecurityDemo
```

Stdout:

```text
processRuns=1
message=class metadata ready
```

### 12.1. Tạo dynamic archive ở giai đoạn build/training

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar ArchiveSecurityDemo
```

Stdout ứng dụng vẫn là:

```text
processRuns=1
message=class metadata ready
```

Khi chạy thành công trong môi trường HotSpot đủ điều kiện, JVM có thể tạo `app.jsa` lúc process kết thúc. **Bước này cần quyền ghi thư mục output**. Sau khi tạo, hãy đo digest và đưa archive vào gói release bất biến. Dynamic archive cần base CDS archive tương thích; **không dùng `-Xshare:off` trong bước dynamic dump**.

### 12.2. Chạy với archive được phát hành

```bash
java -XX:SharedArchiveFile=app.jsa -XX:+VerifySharedSpaces -cp app.jar ArchiveSecurityDemo
```

Ứng dụng vẫn in:

```text
processRuns=1
message=class metadata ready
```

Tùy runtime/JVM flag, phần log chẩn đoán bổ sung có thể xuất hiện. Nếu archive hỏng, không tương thích hoặc bị từ chối, kết quả khởi động phụ thuộc cấu hình và implementation; đừng coi stdout trên là cam kết bất kể lỗi storage.

### 12.3. Chứng minh class ứng dụng load từ archive

```bash
java -XX:SharedArchiveFile=app.jsa -XX:+VerifySharedSpaces -Xlog:class+load=info -cp app.jar ArchiveSecurityDemo
```

Đọc các dòng log chứa `ArchiveSecurityDemo`. Trên HotSpot có dynamic archive phù hợp, log có thể ghi:

```text
[...][info][class,load] ArchiveSecurityDemo source: shared objects file (top)
[...][info][class,load] ArchiveSecurityDemo$Helper source: shared objects file (top)
```

`[...]` được dùng để **rút gọn các trường timestamp/log** trong ví dụ, không phải stdout byte-for-byte. `(top)` cho biết class đến từ archive lớp trên/dynamic trong môi trường dùng hai tầng archive; các JDK hoặc loại archive khác có thể in `source: shared objects file` mà không có `(top)`.

**Một tệp `app.jsa` tồn tại không phải bằng chứng JVM dùng lớp ứng dụng từ tệp đó.** Log `class+load` cho biết class có thật sự lấy từ shared archive hay không. Log này cũng không thay thế xác minh chữ ký/provenance của artifact.

### 12.4. Archive được đánh dấu read-only vẫn dùng được

Khi đã có `app.jsa` hợp lệ, có thể triển khai một bản sao đã được bảo vệ quyền chỉ đọc:

- Bước **build/training** cần tạo ra archive, có quyền ghi ở vùng build.
- Bước **runtime** chỉ đọc archive. Nếu quyền OS cho phép đọc và mapping, JVM có thể dùng file read-only.

Trong một thử nghiệm trên Windows/HotSpot mới, tệp `.jsa` được đánh dấu `IsReadOnly=True` vẫn chạy bình thường với `-XX:+VerifySharedSpaces`; lớp ứng dụng được log là load từ shared archive. **Đừng suy rằng chỉ thuộc tính read-only của file là đủ bảo vệ production.** ACL của thư mục và trust boundary vẫn phải đúng.

Mỗi lượt chạy in `processRuns=1` vì biến static được khởi tạo riêng trong từng process; archive không làm data nghiệp vụ trở thành vùng nhớ chung.

## 13. Thử nghiệm lỗi integrity: chỉ dùng bản sao trong môi trường cô lập

Một bài kiểm tra diagnostic an toàn có thể tạo **bản sao thử nghiệm** của archive rồi thay một byte của bản sao để quan sát JVM từ chối archive hỏng. **Không bao giờ làm điều này với production archive** hoặc với file đang được nhiều JVM sử dụng.

Trong môi trường thử nghiệm tách biệt, người học cần:

1. Tạo `valid.jsa` bằng training JDK.
2. Tạo `corrupted.jsa` dưới thư mục tạm riêng.
3. Chỉ sửa bytes **của bản sao**; ghi nhận SHA-256 bản sao khác bản gốc.
4. Chạy test với `-XX:+VerifySharedSpaces` và `-Xshare:on` để buộc tình huống lỗi hiện ra rõ.
5. Đọc log và exit code, không phụ thuộc exact error string qua mọi JDK.
6. Xóa file thử nghiệm sau khi hoàn tất; không publish bản sửa sang production.

Lệnh test JVM trên archive **đã cố tình làm hỏng trong môi trường thử nghiệm**:

```bash
java -XX:+VerifySharedSpaces -Xshare:on -XX:SharedArchiveFile=corrupted.jsa -cp app.jar ArchiveSecurityDemo
```

Một lần test trên HotSpot hiện đại với archive dynamic bị thay một byte ở vùng được checksum đã báo các dòng:

```text
Checksum verification failed.
Unable to use shared archive.
```

Và process **thoát mã khác 0**. Thông báo cụ thể và vị trí kiểm tra phụ thuộc JDK/loại hỏng; test quan tâm việc không sử dụng archive sai.

**Rất quan trọng:** `-Xshare:on` ép thành công của CDS và theo tài liệu Oracle chủ yếu dành cho **thử nghiệm**, có thể khiến JVM không khởi động nếu archive không tương thích. **Không dùng `-Xshare:on` như cài đặt mặc định cho production** chỉ để buộc ứng dụng dùng archive. Ở môi trường production cần cân nhắc chính sách fail-open (vẫn chạy mà mất tối ưu) hoặc fail-fast ở tầng phân phối **trước khi JVM start**.

### 13.1. Vì sao thử CRC không đủ để chống giả mạo?

Một bit flip ngẫu nhiên có thể bị CRC phát hiện, nhưng attacker có quyền chuẩn bị một archive khác có thể không đơn thuần chỉ gây lỗi checksum. Không có khóa bí mật hoặc public-key trust verification trong `VerifySharedSpaces`.

Để có bảo đảm chống thay thế trái phép, phải đảm bảo:

- nguồn build/deploy đáng tin;
- quản lý quyền các thư mục và artifact;
- digest theo signed/trusted release manifest;
- runtime dùng artifact đã xác minh;
- khóa thay đổi trong quá trình sử dụng theo policy immutable release.

Không lấy kết quả “CRC PASS” làm bằng chứng về danh tính người tạo archive.

## 14. Quy trình publish bất biến

Một mô hình thực tế:

```text
BUILD (tài khoản CI)
  |
  |-- app.jar đã build
  |-- app.jsa được tạo từ JDK/JAR tương ứng
  |-- manifest ghi JDK, app version, digest
  |
  v
TRUSTED ARTIFACT STORAGE
  |
  |-- signed / verified metadata
  |
  v
STAGING AREA (chỉ deployer được ghi)
  |
  |-- xác minh hash + provenance
  |-- smoke test class load / compatibility
  |
  v
RELEASE DIRECTORY KHÔNG CHO RUNTIME GHI
  |
  |-- r1/app.jar + r1/app.jsa
  |-- r2/app.jar + r2/app.jsa
  |
  v
JVM RUNTIME: chỉ đọc đúng một release
```

### 14.1. Stage trước rồi publish, không sửa archive đang dùng

Khi release mới đến:

1. Dùng thư mục staging **khác** với release đang phục vụ request.
2. Xác minh chữ ký/manifest và hash trên bản staging.
3. Smoke test bằng JDK/JAR sẽ chạy production.
4. Thiết lập ownership/ACL cho release mới.
5. Công bố release ở đường dẫn chỉ trusted deployer quản lý.
6. Chuyển service sang archive mới trong lần khởi động/rollout thích hợp.
7. Giữ bản cũ đủ lâu theo chính sách rollback, rồi dọn khi không còn dùng.

Nếu muốn đổi tên/move atomically, chỉ dựa vào thao tác atomic khi filesystem/provider bảo đảm nó (ví dụ cùng filesystem và API hỗ trợ). **Không coi việc copy file qua volume hoặc đổi symlink là giao dịch atomic trong mọi môi trường.**

### 14.2. Vì sao không sửa `app.jsa` tại chỗ?

Nhiều JVM có thể map các vùng của cùng archive file. Thay nội dung file đang được map có thể khiến các tiến trình đang chạy hoặc các tiến trình mới thấy trạng thái không mong muốn theo OS/JVM, dẫn tới lỗi CDS hoặc hành vi không được workflow hỗ trợ.

An toàn hơn là phát hành `app-v2.jsa` hoặc cả thư mục release mới, kiểm thử trước khi chuyển sang. AppCDS archive được xem là một **artifact bất biến** của build, không phải database để cập nhật trực tiếp bằng nhiều writer đồng thời.

### 14.3. Quy trình rollback

Nếu release mới có archive lỗi, đưa ứng dụng quay lại **bộ JDK/JAR/archive đã kiểm chứng cùng nhau**. Không chỉ rollback `app.jar` mà giữ một archive được tạo từ phiên bản khác. Kiểm tra log load class và thời gian khởi động sau rollback.

**Không dùng cùng một tên file bất biến giả** rồi âm thầm overwrite giữa các release. Bảo đảm path và artifact digest được ghi nhận trong deployment manifest.

## 15. Archive compatibility và integrity là hai vấn đề riêng

| Tình trạng | CRC32 | SHA-256 so trusted digest | JVM có dùng được? |
| --- | --- | --- | --- |
| Archive đúng bytes, đúng JDK/JAR | Thường pass | Pass | Có thể dùng nếu các điều kiện CDS khác phù hợp |
| Archive hỏng một số bytes | Có thể fail khi vùng kiểm tra bị ảnh hưởng | Fail | Có thể không dùng, lỗi hoặc fallback |
| Archive đúng bytes nhưng JDK build khác | Có thể pass | Pass | Vẫn có thể bị JVM từ chối vì không tương thích |
| Archive đúng bytes nhưng JAR classpath thay đổi | Có thể pass | Pass | Có thể từ chối archive hoặc không load một số class từ archive |
| Archive bị attacker thay cùng checksum mới | CRC không phải xác thực publisher | Fail nếu trusted digest không đổi | Không nên cho JVM dùng; giải quyết ở trust boundary |
| Archive bị thay và manifest không tin cậy cũng bị thay | CRC có thể pass | Hash khớp manifest giả | Không được kết luận an toàn; cần xác thực manifest |

**Lưu ý:** tính tương thích của archive phụ thuộc JVM implementation/build, runtime image, classpath, JAR, những class đủ điều kiện, loader/module setup và các cờ liên quan. Không có một tệp `.jsa` vạn năng cho mọi JDK/vendor/hệ điều hành.

### 15.1. Tạo archive cùng JDK dùng để chạy

Trong pipeline, record ít nhất:

- JDK vendor, build và runtime feature/update.
- Kiến trúc CPU/hệ điều hành và runtime image.
- Hash của application JAR và các JAR quan trọng trong classpath.
- Các tùy chọn JVM tạo archive và chạy smoke test.
- Hash/manifest provenance của `.jsa`.
- Kết quả smoke test `-Xlog:class+load=info`.
- Mã phiên bản deployment và thời điểm build.

Khi nâng JDK hoặc thay JAR, **xây lại archive** theo chính sách. Không lấy CRC pass làm lý do bỏ qua compatibility validation.

## 16. Chọn hành vi khi archive không có hoặc không đọc được

Một số môi trường coi CDS/AppCDS là **tối ưu**, không phải điều kiện chức năng bắt buộc. Các tình huống có thể có:

- Không thấy file archive.
- User chạy Java thiếu quyền đọc archive.
- Archive hỏng bytes.
- Archive không đúng JDK build.
- JAR/classpath đã thay đổi.
- Nền tảng không hỗ trợ một kiểu archive/tùy chọn cụ thể.
- JVM đọc được archive nhưng một số application classes không được load từ đó.

### 16.1. `-Xshare:auto` so với `-Xshare:on`

Theo Oracle:

- `-Xshare:auto`: thử bật CDS khi có thể, cho phép bỏ qua CDS khi không thể dùng.
- `-Xshare:on`: yêu cầu CDS; nếu không bật được sẽ báo lỗi và JVM có thể thoát. Tài liệu khuyến cáo **không dùng làm cấu hình production mặc định**.
- `-Xshare:off`: tắt CDS; hữu ích khi đo baseline/debug, không phải cách khai thác chia sẻ.
  
Trong vận hành production, có thể sử dụng cấu hình mềm dẻo kèm log/metric phát hiện mất tối ưu. Nếu tổ chức có yêu cầu “không chạy khi artifact chưa được xác thực”, hãy thực hiện **kiểm tra signed provenance/digest ở tầng triển khai hoặc pre-start trust policy**, thay vì nhầm `-Xshare:on` là cơ chế xác thực.

### 16.2. Không được “fallback” bằng cách lấy archive từ nguồn không tin cậy

Khi archive không dùng được, một lựa chọn thường an toàn hơn là khởi động **không có app archive** theo thiết kế đã kiểm thử, chấp nhận startup chậm hơn. Không tự download một tệp `.jsa` từ nguồn bất kỳ chỉ vì nó có cùng tên JAR hoặc làm lỗi biến mất.

Để tiếp tục dùng AppCDS, xây lại archive từ JDK/JAR tin cậy. Trong một pipeline có recovery, hãy giữ logging, audit và cảnh báo về tình huống archive bị từ chối.

## 17. Container và artifact permissions

Container có filesystem layers, mount, UID/GID và runtime security context riêng. Một image chứa `app.jsa` không tự bảo đảm process trong container không thể sửa nó nếu image/mount hoặc UID/GID cho phép ghi.

Khi triển khai:

- Bundle app JAR và archive đã xác minh vào image hoặc mount chỉ đọc.
- Dùng non-root runtime user.
- Giới hạn mount writable vào những đường dẫn ứng dụng thực sự cần (log, tmp, cache riêng).
- Không dùng chung thư mục writable cho app uploads và archive.
- Nếu có nhiều container cùng node, bảo vệ backing archive và provenance của từng image/release.
- Nếu không cùng node, không nói chúng chia sẻ **cùng trang RAM vật lý** chỉ vì tên file giống nhau.
- Kiểm tra image digest, JDK build và archive/JAR compatibility theo từng release.
- Giám sát exit code, CDS warnings và fallback trong rolling update.

**Read-only root filesystem** của container là một lớp giảm rủi ro, nhưng không thay thế kiểm soát quyền trong image pipeline và nguồn base image. Nếu chính image đã bị thay đổi trước deploy, read-only chỉ giữ nguyên phiên bản giả mạo đó.

### 17.1. Không lưu bí mật vào archive với suy nghĩ nó được mã hóa

`.jsa` là một artifact JVM, **không phải kho bí mật được mã hóa**. Không cố nhúng credential hoặc dữ liệu người dùng vào luồng training rồi coi shared archive là phương án bảo vệ bí mật. Quy tắc secret management của ứng dụng phải độc lập với CDS.

## 18. Quan sát và audit

Để phân biệt “quyền đúng nhưng archive không được dùng” với “archive bị sửa”, hãy thu thập dữ liệu có cấu trúc:

| Dữ liệu | Tại sao hữu ích |
| --- | --- |
| JDK vendor/version/build | Archive có thể không tương thích khi runtime khác |
| Đường dẫn/ID release của archive | Biết process được cấu hình dùng bản nào |
| SHA-256 artifact từ trusted manifest | Xác minh đúng bytes của release |
| Classpath/JAR digest | Phát hiện JAR thay đổi so với archive |
| UID/GID/ACL của runtime và release dir | Debug permission denied và nguy cơ write access |
| Log `-Xlog:cds=info` | Thông tin JVM nạp, map, hoặc từ chối archive |
| Log `-Xlog:class+load=info` cho class ứng dụng | Xác nhận class có source là shared objects file |
| Startup exit code và stderr | Phân biệt lỗi nạp archive với lỗi business |
| Thay đổi release và audit event | Điều tra ai/when đã deploy hoặc thay artifact |

Cờ hữu ích trong môi trường thử nghiệm:

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveSecurityDemo
```

```bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveSecurityDemo
```

Log đầy đủ có thể rất lớn và format thay đổi theo JDK. Bật có chọn lọc trong smoke test hoặc chẩn đoán, không bắt buộc log class loading chi tiết cho mọi request production.

### 18.1. Hạn chế tiết lộ thông tin

Đường dẫn build, tên user/service, Java home, danh sách JAR và classpath có thể chứa thông tin hạ tầng. Audit cần đủ dữ liệu để gỡ lỗi nhưng không tự động log secrets, biến môi trường nhạy cảm hoặc nội dung người dùng.

## 19. Xử lý sự cố theo loại lỗi

### 19.1. Permission denied

Triệu chứng: JVM không thể đọc/map archive hoặc không thể ghi archive ở bước tạo.

Kiểm tra:

1. Bước đang chạy là **dump** (cần quyền tạo/ghi) hay **runtime** (cần đọc)?
2. Process chạy dưới identity nào?
3. Tất cả thư mục cha có cho traverse không?
4. File mode/ACL/ownership có đúng không?
5. Có symlink hoặc mount path khác kỳ vọng không?
6. SELinux/AppArmor/container policy có chặn thao tác không?
7. File đã được publish dưới đúng release path chưa?

**Không chữa bằng cách cho runtime user Full Control cả thư mục JDK/release.** Hãy cấp đúng quyền tối thiểu cho role cần thao tác.

### 19.2. Checksum verification failed

Triệu chứng: log với `-XX:+VerifySharedSpaces` báo checksum không khớp.

Hướng xử lý:

1. Coi archive này **không còn tin cậy để tiếp tục dùng**.
2. Không sửa byte thủ công hoặc tự bỏ qua log để tiếp tục coi nó là artifact được phê duyệt.
3. Đối chiếu digest của bản đang dùng với manifest đáng tin.
4. Kiểm tra truyền tải, storage, lỗi hệ thống, quyền sửa và deployment event.
5. Thay bằng artifact đã kiểm chứng hoặc build lại từ JDK/JAR tin cậy.
6. Chạy lại smoke test và xem log class load.

**Checksum fail có thể do hỏng vô ý, chưa đủ kết luận có tấn công.** Nếu có dấu hiệu sửa trái phép, mở quy trình xử lý sự cố bảo mật theo chính sách tổ chức.

### 19.3. Hash khớp nhưng archive không dùng được

Nếu SHA-256 khớp bản đã phê duyệt mà JVM vẫn từ chối, xem:

- phiên bản JDK/vendor/kiến trúc khác khi dump;
- classpath/module-path/JAR bị thay;
- cờ VM không tương thích;
- thiếu base archive cho dynamic archive;
- custom classloader hoặc class không đủ điều kiện;
- quyền đọc/mapping khác;
- runtime CDS không được bật hoặc có cờ cấm.

**Tính nguyên vẹn bytes không bảo đảm tính tương thích runtime.**

### 19.4. JVM chạy được nhưng AppCDS không hoạt động

Một JVM có thể bỏ qua archive theo cấu hình mềm dẻo và vẫn chạy ứng dụng. Hãy kiểm tra `-Xlog:class+load=info`: application classes có lấy từ shared archive hay JAR không? Nếu chỉ có core classes được chia sẻ từ default archive, chưa chắc AppCDS của chính ứng dụng hoạt động.

Đây là vấn đề **availability/performance**, chưa nhất thiết là vi phạm tính toàn vẹn; không tự đưa ra cảnh báo bảo mật chỉ vì startup chậm một lần.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Archive memory-map read-only nên file trên đĩa chắc chắn không sửa được.” | Memory protection và file/dir permissions là hai lớp khác nhau |
| “`chmod 0444 app.jsa` đủ bảo vệ kho dù thư mục cha writable cho tất cả.” | Người có quyền thay thế entry trong thư mục có thể vẫn thay path |
| “`IsReadOnly=True` trên Windows chứng minh ACL secure.” | Không: cần kiểm tra owner, directory ACL và quyền delete/rename |
| “Runtime user phải có quyền ghi archive để đọc AppCDS.” | Bình thường runtime chỉ cần quyền đọc; writer là build/deployer |
| “CRC32 là chữ ký số của archive.” | Không: chỉ kiểm tra hỏng vô ý, không xác thực nguồn |
| “Hash vừa tính từ file là bằng chứng file đáng tin.” | Chỉ có ý nghĩa trust nếu so với digest/manifest đã xác thực |
| “JAR được ký thì `app.jsa` tự động có chữ ký ấy.” | Không: JAR signature và archive artifact là hai đối tượng khác nhau |
| “SHA-256 PASS nghĩa là JVM chắc chắn load AppCDS.” | Không: còn JDK/JAR/classpath/flags compatibility |
| “`-Xshare:on` là bật chế độ bảo mật nghiêm ngặt của archive.” | Không: cờ yêu cầu CDS hoạt động, chủ yếu phục vụ test |
| “Hai JVM đang dùng cùng .jsa thì chúng chia sẻ heap.” | Không: chỉ một số class metadata/pages phù hợp; heap riêng |
| “Có file .jsa là AppCDS đang hoạt động.” | Phải kiểm tra log `shared objects file` cho class cần thiết |
| “Không cần bảo vệ directory vì file read-only.” | Không: đổi tên, symlink, thay file có thể là rủi ro |
| “Đổi JDK nhưng giữ archive cũ vì hash không đổi.” | Không bảo đảm tương thích |
| “Có thể cập nhật file .jsa tại chỗ khi nhiều process dùng.” | Không phải workflow an toàn; phát hành immutable version mới |
| “Một archive dùng được trên mọi host/JDK/vendor/CPU.” | Không: format và tính tương thích phụ thuộc JVM/environment |
| “Archive bị từ chối chắc chắn do tấn công.” | Có thể là hỏng, mismatch, quyền, flags hoặc lỗi storage |
| “Chỉ có app ở một container thì archive không cần kiểm tra.” | Vẫn là artifact đầu vào JVM, cần provenance/permissions |
| “Có thể verify ở đầu `main` trước khi JVM nạp archive.” | Không: JVM có thể đọc archive trước khi `main` chạy |
| “CRC32 và SHA-256 đều cho biết publisher là ai.” | Cả hai không chứng thực publisher nếu không có trust/signature |
| “Cho thư mục release toàn quyền ghi giúp hệ thống dễ vận hành hơn.” | Làm rộng attack surface và rủi ro lỗi thao tác |
| “Archive read-only là cơ chế giữ secrets an toàn.” | Không: archive không phải vault/bộ mã hóa bí mật |

## 21. Bài tập có lời giải

### Bài 1 — Runtime user có quyền gì?

Một service Java chỉ cần khởi động với `-XX:SharedArchiveFile=app.jsa`. Runtime user có cần được quyền ghi và xóa `app.jsa` không?

**Đáp án:** không. Thông thường chỉ cần quyền đọc và quyền traverse các thư mục cha, còn quyền viết/tạo do build/trusted deployer đảm nhiệm.

### Bài 2 — Chỉ chmod file

`app.jsa` được đặt mode `0444` nhưng thư mục chứa file lại cho một user không tin cậy quyền tạo/xóa entry. Đã an toàn chưa?

**Đáp án:** chưa. Người đó có thể có khả năng thay thế entry của file theo quyền thư mục. Phải bảo vệ cả cây thư mục, owner, symlink và rollout path.

### Bài 3 — CRC32

Bật `-XX:+VerifySharedSpaces`. Điều này có chứng minh archive do nhà phát hành được ủy quyền tạo không?

**Đáp án:** không. CRC32 là checksum phát hiện hỏng dữ liệu vô ý. Xác thực nguồn cần artifact provenance, trusted/signed manifest và access control.

### Bài 4 — Hash tự tính

Một script tải `app.jsa` và `app.jsa.sha256` từ cùng một nguồn không tin cậy, rồi `sha256sum -c` báo OK. Có thể coi archive đã được xác thực không?

**Đáp án:** không. Attacker có thể thay cả archive và file checksum. Hash cần được so với manifest/chuỗi chứng thực từ nguồn tin cậy.

### Bài 5 — CRC pass nhưng archive không chạy

SHA-256 cũng khớp. JVM vẫn báo archive không dùng được vì JDK đã nâng cấp. Có mâu thuẫn không?

**Đáp án:** không. Integrity bytes và runtime compatibility là hai điều kiện riêng biệt.

### Bài 6 — Thời điểm verify

Bạn gọi code kiểm tra SHA-256 trong `public static void main` của ứng dụng. Việc này có bảo đảm JVM chưa đọc archive không?

**Đáp án:** không. Archive có thể được đọc trong quá trình JVM startup trước `main`. Xác minh trước tại deploy pipeline/pre-start trusted wrapper.

### Bài 7 — Đường dẫn bất biến

Vì sao dùng `release-A/app.jsa` và `release-B/app.jsa` tốt hơn ghi đè cùng `release/app.jsa` khi có nhiều JVM?

**Đáp án:** có thể build và verify trước khi publish, không sửa tệp đang được nhiều JVM map, và rollback về một bộ JDK/JAR/archive đã được kiểm chứng.

### Bài 8 — `-Xshare:on`

Nếu archive bị hỏng mà JVM được chạy với `-Xshare:on` và `-XX:+VerifySharedSpaces`, điều gì có thể xảy ra?

**Đáp án:** JVM có thể báo checksum/mapping error và thoát vì `on` yêu cầu CDS. Cờ này phù hợp test có kiểm soát, không là mặc định production.

### Bài 9 — Windows read-only

`Get-Item .\app.jsa` báo `IsReadOnly=True`. Có chắc user không thể xóa/thay file qua đường dẫn đó không?

**Đáp án:** không. Cần kiểm tra ACL của file, thư mục, quyền delete/rename và identity process. Read-only attribute không thay thế least-privilege ACL.

### Bài 10 — Kiểm chứng class app

Có `app.jsa` và JVM chạy tốt. Lệnh nào giúp chứng minh một class app load từ archive?

**Đáp án:** bật `-Xlog:class+load=info` và tìm tên class với `source: shared objects file`, đồng thời xem log CDS khi có lỗi.

### Bài 11 — Java heap

Hai JVM cùng đọc một archive và một `static int counter` trong cả hai process đều tăng một lần. Counter có trở thành 2 chung toàn hệ thống không?

**Đáp án:** không. Mỗi process có state tĩnh riêng; AppCDS chỉ chia sẻ một số metadata/trang read-only, không chia sẻ dữ liệu heap.

### Bài 12 — AppCDS trong container

Hai container trên hai node có cùng `/app/app.jsa`. Chúng có cùng trang RAM vật lý không?

**Đáp án:** không. RAM vật lý thuộc từng host; AppCDS không cung cấp chia sẻ RAM xuyên node. Mỗi container vẫn cần artifact trust và compatibility của riêng runtime.

### Bài 13 — Chọn phương án xử lý checksum fail

Bản `app.jsa` ở production không khớp digest của manifest tin cậy. Nên sửa checksum file để nó khớp archive hiện có?

**Đáp án:** không. Coi archive là artifact không đạt kiểm tra, cách ly, tìm nguyên nhân, tải bản đã xác minh hoặc tạo lại archive từ nguồn tin cậy rồi deploy bằng release mới.

### Bài 14 — Đổi JAR

Tạo archive từ `app.jar` phiên bản A; triển khai `app.jar` phiên bản B nhưng giữ archive của A. Archive có thể không được dùng vì sao?

**Đáp án:** JVM kiểm tra tính tương thích nguồn class/classpath; khi JAR thay đổi có thể từ chối archive hoặc bỏ qua class tương ứng. Build lại archive cùng JAR, JDK và flags của release B.

### Bài 15 — Môi trường ít quyền

Runtime chỉ có quyền đọc file `app.jsa` nhưng không traverse được thư mục cha. Có thể đọc archive không?

**Đáp án:** trên POSIX thông thường không. Muốn mở file cần quyền phù hợp trên cả thành phần đường dẫn, không riêng permission của file.

### Bài 16 — Test archive bị sửa

Tại sao chỉ làm thử trên bản sao tạm của archive?

**Đáp án:** archive là artifact đầu vào của JVM và có thể được nhiều tiến trình dùng. Sửa bản production có thể gây lỗi startup hoặc ảnh hưởng rollout; test hỏng bytes phải cách ly để không làm gián đoạn dịch vụ.

### Bài 17 — Vì sao không cấp `Full Control`?

Service Java gặp lỗi `Access denied` khi tải archive. Có nên cấp `Everyone:F` cho thư mục release?

**Đáp án:** không. Hãy xác định quyền đọc/traverse bị thiếu và cấp tối thiểu cho runtime user, giữ quyền ghi/xóa chỉ cho deployer tin cậy.

### Bài 18 — Hash và source trust

Một archive có SHA-256 đúng nhưng tải từ URL không được tổ chức phê duyệt. Đã đủ tin cậy chưa?

**Đáp án:** còn phụ thuộc digest đã được xác thực độc lập hay chưa. Nếu digest lấy từ một signed/trusted manifest của release thì việc khớp bytes có ý nghĩa; nếu chỉ so với dữ liệu từ nguồn không tin cậy thì chưa.

## 22. Checklist trước khi đưa vào production

1. **Archive xuất phát từ JDK/JAR/training environment đáng tin?**
2. **Đã phân biệt user tạo archive với user chạy ứng dụng?**
3. **Runtime user chỉ có quyền đọc thay vì ghi/sửa/xóa release?**
4. **Các thư mục cha và symlink được bảo vệ khỏi đổi path trái phép?**
5. **Đã rà soát ACL/ownership thực tế trên OS mục tiêu?**
6. **Có ngăn thư mục upload/user-writable trở thành archive location?**
7. **Default CDS archive của JDK nằm trong runtime image được quản lý?**
8. **Application archive được version theo JDK, JAR, runtime image?**
9. **Có trusted/signed manifest hoặc trusted artifact digest?**
10. **Có kiểm tra SHA-256 với digest từ kênh tin cậy trước publish?**
11. **Có hiểu CRC32 không xác thực publisher không?**
12. **Nếu dùng `VerifySharedSpaces`, đã hiểu mục tiêu phát hiện hỏng vô ý?**
13. **Có chạy smoke test với đúng JDK/JAR/classpath?**
14. **Có xác nhận application class load từ `shared objects file`?**
15. **Có tránh `-Xshare:on` trong cấu hình mặc định production?**
16. **Có thiết kế fallback phù hợp khi chỉ mất tối ưu AppCDS?**
17. **Có chính sách fail-fast ở bước trust verification nếu artifact không xác thực?**
18. **Có stage trước khi publish, không sửa archive đang dùng?**
19. **Có versioned release directories và quy trình rollback?**
20. **Có bảo vệ archive trong image/container bằng non-root và file permissions?**
21. **Có kiểm tra tình huống cùng tên file nhưng khác backing archive/host?**
22. **Có phân biệt lỗi integrity, lỗi compatibility và lỗi permission?**
23. **Có ghi nhận JDK vendor/build, digest và audit deploy event?**
24. **Có tránh tiết lộ secret qua archive hoặc log environment không cần thiết?**
25. **Có test archive bị hỏng chỉ trong môi trường thử nghiệm cô lập?**
26. **Có dùng công cụ JDK/tool versions còn được hỗ trợ?**
27. **Có hiểu code trong `main` không đủ sớm để bảo vệ pre-start archive?**
28. **Có quy trình điều tra khi digest đổi hoặc archive bị thay ngoài kế hoạch?**

## 23. Tổng kết

**Tính chia sẻ của AppCDS nằm ở các trang metadata lớp có thể memory-map read-only giữa nhiều JVM phù hợp; điều đó không tự bảo vệ tệp archive trên đĩa**. Muốn vận hành an toàn, hãy cấp quyền theo vai trò, bảo vệ thư mục cha và đường dẫn release, tạo archive từ JDK/JAR tin cậy, kiểm tra digest/provenance trước khi phát hành và không sửa archive đã publish.

Cờ `-XX:+VerifySharedSpaces` của HotSpot có thể phát hiện hỏng dữ liệu qua CRC32, nhưng **CRC32 không phải xác thực mật mã**. SHA-256 chỉ có giá trị chứng minh artifact khớp bản được phê duyệt khi expected digest đến từ một nguồn tin cậy; signed manifest/trusted distribution và quyền OS giải quyết thêm vấn đề nguồn gốc. Archive đạt kiểm tra integrity vẫn có thể không tương thích với JDK/JAR, nên phải smoke test và theo dõi log `cds`/`class+load`.

Với JDK hiện đại, có thể tạo dynamic archive bằng `-XX:ArchiveClassesAtExit`, sử dụng bằng `-XX:SharedArchiveFile` và kiểm chứng ứng dụng bằng `-Xlog:class+load=info`. Hãy coi `.jsa` là **artifact release bất biến**, cấp quyền đọc cho runtime, bảo vệ quyền ghi cho deployer và giữ rollback/fallback rõ ràng. Đây là cách khai thác lợi ích startup/memory của AppCDS mà không biến một công cụ tối ưu hóa thành rủi ro vận hành hoặc bảo mật.

### Tài liệu kỹ thuật chính thức

- [Oracle Java SE 17 — java command (VerifySharedSpaces, AppCDS, options)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html)
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html)
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310)
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350)
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [Java SE 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html)
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)