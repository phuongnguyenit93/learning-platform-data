# Kiểm tra độ tin cậy của agent trước khi triển khai

## 1. Agent là một phần mã thực thi của ứng dụng

Java agent không chỉ là tệp cấu hình quan sát. Nó chạy trong JVM của ứng dụng, có thể đăng ký biến đổi bytecode, bổ sung lớp hỗ trợ, tạo luồng, đọc dữ liệu mà tiến trình nhìn thấy và gửi dữ liệu ra ngoài theo mã/cấu hình của nó.

Do đó, “JVM nạp được JAR” chưa đủ để kết luận agent đáng tin cậy. Cần có bằng chứng cho ba câu hỏi:

1. **Đúng phần mềm:** JAR đến từ đâu, có đúng phiên bản đã được kiểm chứng và có bị thay đổi không?
2. **Đúng hành vi:** agent thu thập, thay đổi và gửi những gì; có quyền hạn/phụ thuộc nào không cần thiết?
3. **Vận hành được:** ứng dụng vẫn đúng chức năng, ổn định và có cách khôi phục khi agent lỗi không?

Đặc tả Java đặt trách nhiệm kiểm chứng độ tin cậy, bao gồm nội dung và cấu trúc agent JAR, lên bên triển khai. Xem [đặc tả java.lang.instrument](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html).

## 2. Xác định chính xác bản sẽ triển khai

Trước tiên lập một bản ghi đủ nhận diện bản phát hành:

| Thông tin | Mục đích |
| --- | --- |
| Tên sản phẩm, nhà cung cấp/chủ sở hữu | Biết nguồn chịu trách nhiệm và nơi nhận thông tin sửa lỗi |
| Phiên bản cụ thể | Tránh một tên tệp che nhiều nội dung khác nhau |
| Nguồn phát hành hoặc quy trình build | Truy ngược từ JAR tới nguồn và quá trình tạo |
| SHA-256 của JAR | Đối chiếu chính xác byte của artifact |
| JDK, hệ điều hành, kiến trúc đã thử | Khoanh phạm vi tương thích có bằng chứng |
| Các JAR phụ, helper, thư viện native | Không bỏ sót mã thực thi ngoài JAR chính |
| Cấu hình hiệu lực và đích gửi dữ liệu | Biết hành vi nào thực sự được bật |

Cố định một phiên bản và lưu artifact ở nơi kiểm soát được. Một đường dẫn như `agent.jar` có thể giữ nguyên trong khi nội dung bị thay; tên tệp không phải định danh đủ mạnh.

Nếu agent tự tải thêm plugin, helper hoặc cấu hình có thể đổi hành vi, việc kiểm chứng phải bao gồm nguồn và chính sách cập nhật của những thành phần đó. Hash JAR chính không bao phủ các tệp được tải về sau.

Không đưa JAR chưa rõ nguồn gốc vào JVM sản xuất chỉ để “thử xem nó làm gì”. Bắt đầu bằng kiểm tra tĩnh và môi trường thử nghiệm có dữ liệu/quyền hạn phù hợp.

## 3. Hash, chữ ký và nguồn gốc chứng minh những điều khác nhau

### SHA-256: có đúng byte đã được chấp nhận không?

Trên PowerShell:

```powershell
Get-FileHash -LiteralPath .\agent.jar -Algorithm SHA256
```

Kết quả chỉ hữu ích cho xác thực khi so với giá trị mong đợi lấy từ nguồn đã xác minh hoặc quy trình phát hành được kiểm soát. Nếu tải một JAR không rõ nguồn rồi tự tính hash của nó, bạn mới ghi nhận nội dung hiện tại, chưa chứng minh nội dung đó đáng tin.

Tương tự, JAR và tệp checksum cùng đến từ một nguồn đã bị thay đổi có thể khớp nhau. Nguồn của giá trị đối chiếu quan trọng không kém thuật toán hash.

### Chữ ký JAR: dữ liệu được ký có bị đổi và ai ký?

Với bản phát hành có chữ ký JAR, dùng công cụ JDK:

```shell
jarsigner -verify -strict -verbose -certs agent.jar
```

Đọc cả mã thoát, cảnh báo, danh tính người ký và phạm vi các mục được ký. Đừng chỉ tìm một dòng có chữ “verified”. Theo chính sách sử dụng, cần xác minh chuỗi chứng thư/nguồn khóa tin cậy, thời hạn và những cảnh báo liên quan; không tự tắt kiểm tra để đạt kết quả xanh.

Không có chữ ký không tự chứng minh JAR độc hại; nó có thể là bản build nội bộ được xác thực bằng quy trình khác. Ngược lại, chữ ký hợp lệ không chứng minh thuật toán hay hành vi của agent an toàn. Nó cung cấp bằng chứng về dữ liệu được ký và người ký, không thay thế kiểm thử.

Một JAR có thể có nội dung không được chữ ký hiện có bao phủ. Vì vậy cần xem phạm vi ký và toàn bộ artifact, không coi “có tệp chữ ký trong META-INF” là đã kiểm chứng. Xem [hướng dẫn jarsigner](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jarsigner.html) và [đặc tả signed JAR](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html).

## 4. Đọc cấu trúc và khả năng agent yêu cầu

Liệt kê nội dung trước khi chạy:

```shell
jar --list --file agent.jar
```

Kiểm tra manifest và đối chiếu với tài liệu/mã nguồn của đúng phiên bản:

| Thuộc tính/nội dung | Câu hỏi cần trả lời |
| --- | --- |
| `Premain-Class` | Có đúng lớp khởi động đã được công bố không? |
| `Agent-Class` | Agent có cơ chế nạp vào JVM đang chạy không, và có cần dùng trong môi trường này không? |
| `Can-Redefine-Classes` | Vì sao cần cung cấp lại định nghĩa lớp đã nạp? |
| `Can-Retransform-Classes` | Vì sao cần biến đổi lại lớp đã nạp? |
| `Can-Set-Native-Method-Prefix` | Có chức năng native nào thực sự cần khả năng này? |
| `Boot-Class-Path`, helper JAR | Những lớp nào được đưa vào phạm vi bootstrap? |
| Thư viện đóng gói kèm | Có danh sách phiên bản, nguồn và tình trạng cập nhật không? |

Các thuộc tính khả năng là yêu cầu chức năng, **không phải một sandbox quyền hạn**. Agent không khai báo retransformation vẫn là mã chạy cùng tiến trình và vẫn có thể làm nhiều việc khác. Đừng kết luận agent “ít quyền” chỉ bằng cách đếm các cờ `Can-...`.

Danh sách JAR cũng không tự giải thích mọi hành vi. Với JAR gộp thư viện hoặc có tài nguyên thực thi lồng bên trong, cần kiểm kê các thành phần thực sự được sử dụng. Đối chiếu thông tin phụ thuộc, cảnh báo bảo mật và bản sửa lỗi hiện hành của đúng phiên bản; một lần quét không chứng minh vĩnh viễn rằng không có vấn đề.

## 5. Xác định phạm vi dữ liệu và tác động

Đọc cấu hình hiệu lực, không chỉ cấu hình mặc định trong tài liệu:

- Agent có thu thập URL, header, nội dung request/response, tham số SQL hoặc giá trị biến không?
- Có lọc dữ liệu nhạy cảm trước khi ghi log/gửi đi không? Bộ lọc áp dụng cho đường lỗi và chẩn đoán hay chỉ đường thành công?
- Đích gửi dữ liệu thuộc đâu? Có xác thực máy chủ, mã hóa đường truyền và giới hạn kết nối không?
- Agent có đọc tệp, biến môi trường, tạo tiến trình con hoặc tải mã mới không? Những hành vi này có phù hợp mục tiêu sử dụng không?
- Khi không thể gửi dữ liệu, hàng đợi có giới hạn và có chính sách bỏ dữ liệu rõ ràng không?

Kiểm tra bằng dữ liệu thử có dấu nhận diện để biết điều gì xuất hiện ở đầu ra. Không dùng thông tin thật nhạy cảm chỉ để kiểm chứng tính năng lọc.

Giữ thông tin xác thực trong cơ chế cấu hình bí mật phù hợp, không đặt token trực tiếp vào tùy chọn dòng lệnh hoặc log khởi động. Agent chạy cùng JVM; giới hạn quyền của tài khoản/container và mạng có ích, nhưng không tạo ra ranh giới cách ly giữa agent và ứng dụng trong cùng tiến trình.

Với agent tự phát triển, xem kỹ vùng chọn lớp để biến đổi, các phụ thuộc dùng trong callback, cách xử lý lỗi và trạng thái sức khỏe khi một phần phép đo bị bỏ qua. Agent không được âm thầm báo “hoạt động bình thường” trong khi một số lớp quan trọng không được instrument.

## 6. Kiểm chứng tương thích và độ ổn định bằng thử nghiệm

Đưa đúng JAR và cấu hình dự kiến vào môi trường gần sản xuất nhất có thể. Ma trận tối thiểu phụ thuộc ứng dụng, nhưng cần xét:

| Nhóm thử | Bằng chứng nên thu |
| --- | --- |
| Khởi động và tắt | Vào được trạng thái sẵn sàng, đóng đúng thời hạn, không mắc kẹt do luồng agent |
| Đúng chức năng | Giá trị trả về, ngoại lệ, tác dụng phụ và giao thức không bị thay đổi ngoài thiết kế |
| JDK và class file | Phiên bản JVM và phiên bản bytecode mà công cụ thực sự xử lý được |
| Bộ nạp lớp/module | Helper nhìn thấy đúng nơi, không trùng kiểu, không cần mở package quá phạm vi cần thiết |
| Nhiều agent | Thử đúng tập agent và đúng thứ tự triển khai cùng nhau |
| Tải và chạy lâu | CPU, bộ nhớ, GC, độ trễ, luồng và dấu hiệu giữ bộ nạp lớp ngoài ý muốn |
| Lỗi hệ thống bên ngoài | Mất mạng, đích thu thập chậm, thông tin xác thực hết hạn, phản hồi bất thường |
| Cấu hình không hợp lệ | Có lỗi rõ ràng và hành vi đúng chính sách khi thiếu/sai cấu hình |

Nếu ứng dụng dùng virtual thread, nhiều bộ nạp plugin hoặc framework sinh lớp động, thử đúng các đường đó. “Chạy được một chương trình main nhỏ” không bao phủ môi trường thực tế.

Đối với hiệu năng, so sánh cùng workload, tài nguyên và giai đoạn khởi động ổn định giữa **không agent** và **có agent**. Xem phân bố độ trễ, thông lượng và tài nguyên theo nhiều lần chạy, không rút kết luận từ một phép đo duy nhất. Chọn trước tiêu chí chấp nhận theo yêu cầu của ứng dụng, thay vì đưa ra một tỷ lệ “an toàn” dùng cho mọi hệ thống.

### Thống nhất chính sách khi agent lỗi

Nếu agent chỉ phục vụ quan sát, có thể cho ứng dụng tiếp tục trong một số lỗi, nhưng phải báo rõ mức thu thập bị giảm. Nếu agent đảm nhiệm yêu cầu bắt buộc, không được tự động bỏ qua chức năng đó mà vẫn coi hệ thống đã đáp ứng yêu cầu.

Ngoại lệ trong `transform` không phải cơ chế chắc chắn chặn nạp lớp: JVM vẫn tiếp tục chuỗi bộ biến đổi theo hợp đồng. Ngược lại, lỗi không được xử lý ở `premain` có thể làm ứng dụng không khởi động. Hãy kiểm thử các tình huống tương ứng, không suy luận chỉ từ tên ngoại lệ.

## 7. Ví dụ Java 17+: đối chiếu checksum và đọc metadata mà không nạp agent

Chương trình sau thực hiện một phần kiểm tra tĩnh:

1. Đọc SHA-256 đã được chấp nhận từ tệp riêng.
2. So với byte hiện tại của JAR.
3. Kiểm tra có manifest, `Premain-Class` và mục class tương ứng.

Nó **không** tải lớp agent, không gọi `premain`, không kiểm chữ ký và không phân tích tính an toàn của mã. Có mục `.class` trong JAR cũng chưa chứng minh lớp đó có chữ ký phương thức hợp lệ hoặc mọi phụ thuộc đều có mặt.

### Bộ kiểm tra

Tệp `AgentPreflight.java`:

```java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.JarFile;

public final class AgentPreflight {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            reject("usage: java AgentPreflight agent.jar approved.sha256");
        }

        Path jarPath = Path.of(args[0]);
        String expected = Files.readString(Path.of(args[1])).strip();
        if (!expected.matches("[0-9a-fA-F]{64}")) {
            reject("baseline=INVALID");
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (DigestInputStream input = new DigestInputStream(
                Files.newInputStream(jarPath), digest)) {
            input.transferTo(OutputStream.nullOutputStream());
        }
        String actual = HexFormat.of().formatHex(digest.digest());
        if (!actual.equalsIgnoreCase(expected)) {
            reject("checksum=MISMATCH");
        }

        // Signature verification is deliberately outside this example.
        try (JarFile jar = new JarFile(jarPath.toFile(), false)) {
            if (jar.getManifest() == null) {
                reject("manifest=MISSING");
            }
            String premain = jar.getManifest()
                    .getMainAttributes().getValue("Premain-Class");
            if (premain == null || premain.isBlank()) {
                reject("premain=MISSING");
            }
            if (jar.getJarEntry(premain.replace('.', '/') + ".class") == null) {
                reject("premainEntry=MISSING");
            }
            System.out.println("checksum=MATCH");
            System.out.println("premain=" + premain);
            System.out.println("premainEntry=PRESENT");
            System.out.println("staticChecks=passed");
        }
    }

    private static void reject(String message) {
        System.err.println(message);
        System.exit(2);
    }
}
```

`JarFile(..., false)` được dùng có chủ đích: ví dụ này đọc metadata, không thực hiện xác thực chữ ký. Không sửa dòng đó thành `true` rồi kết luận toàn bộ chữ ký đã được kiểm đầy đủ chỉ vì mở JAR thành công; việc xác thực các mục ký còn liên quan đọc nội dung và chính sách người ký.

Khi bị từ chối theo các điều kiện trong ví dụ, chương trình ghi thông báo ra stderr và thoát với mã `2`. Lỗi I/O không được xử lý cũng làm lệnh thất bại; pipeline phải coi mã thoát khác `0` là không đạt bước kiểm tra này.

### Tạo một agent mẫu có mã nguồn tự kiểm soát

Tệp `src/demo/agent/DemoAgent.java`:

```java
package demo.agent;

public final class DemoAgent {
    public static void premain(String options) {
        System.out.println("agent: initialized");
    }
}
```

Tệp `agent-manifest.mf`, không có BOM và có xuống dòng cuối:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.DemoAgent

```

Biên dịch và đóng gói:

```shell
javac --release 17 -d out/agent src/demo/agent/DemoAgent.java
jar --create --file demo-agent.jar --manifest agent-manifest.mf -C out/agent .
javac --release 17 -d out/check AgentPreflight.java
```

Trong thực nghiệm này, bạn vừa đọc mã nguồn và tự tạo artifact mẫu. Ghi lại checksum của artifact đó làm mốc cho phép thử trên PowerShell:

```powershell
$approvedHash = (Get-FileHash -LiteralPath .\demo-agent.jar -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath .\approved-agent.sha256 -Value $approvedHash -Encoding ascii
java -cp out/check AgentPreflight demo-agent.jar approved-agent.sha256
```

Stdout:

```text
checksum=MATCH
premain=demo.agent.DemoAgent
premainEntry=PRESENT
staticChecks=passed
```

Không có dòng `agent: initialized`: lệnh kiểm tra không dùng `-javaagent` và không nạp agent để chạy. Tệp agent mẫu này chưa được ký; nó không đáp ứng một chính sách yêu cầu chữ ký chỉ nhờ kết quả kiểm tra tĩnh trên.

**Trong triển khai thật, tệp checksum phải đến từ nguồn hoặc quy trình đã được xác minh.** Không tự tính checksum của một JAR không rõ nguồn rồi dùng nó làm “bằng chứng đã duyệt”. Cách tạo mốc trong ví dụ chỉ nhằm thiết lập thực nghiệm với mã nguồn do bạn vừa kiểm soát.

Thử nhánh không khớp bằng một tệp đối chiếu cố ý sai:

```powershell
Set-Content -LiteralPath .\wrong.sha256 -Value ('0' * 64) -Encoding ascii
java -cp out/check AgentPreflight demo-agent.jar wrong.sha256
$LASTEXITCODE
```

Lệnh Java ghi `checksum=MISMATCH` ra stderr; PowerShell hiển thị mã thoát `2`. Đây là phép thử lỗi, không phải sửa mốc được chấp nhận để bỏ qua sai lệch.

Cả nhánh khớp và không khớp đã được kiểm tra với mã biên dịch `--release 17` trên Zulu OpenJDK 24.0.2.

Công cụ này là ví dụ học tập, không phải bộ xác thực artifact hoàn chỉnh: chưa kiểm cấu trúc class file, tất cả phụ thuộc, chữ ký, JAR lồng, hành vi thực thi hoặc thay đổi tệp đồng thời. Trong quy trình thật, giữ artifact bất biến sau kiểm chứng và đối chiếu lại đúng byte ở điểm triển khai.

## 8. Chuẩn bị triển khai có kiểm soát và khôi phục

Sau khi các bước kiểm chứng đạt yêu cầu, triển khai thử trên phạm vi nhỏ với đúng artifact và cấu hình đã thử. Quan sát đồng thời sức khỏe ứng dụng và sức khỏe agent; việc agent vẫn gửi một ít dữ liệu không chứng minh ứng dụng không bị ảnh hưởng.

Ghi lại tối thiểu: hash JAR, phiên bản/cấu hình, JDK, lệnh khởi động hiệu lực, kết quả kiểm thử, mức thay đổi hiệu năng và dấu hiệu cần dừng mở rộng.

Chuẩn bị đường khôi phục trước khi mở rộng:

- Giữ bản agent/cấu hình đã ổn định trước đó.
- Biết cách khởi động lại ứng dụng với phiên bản cũ hoặc không có agent khi chính sách cho phép.
- Xác định ai theo dõi và dấu hiệu nào kích hoạt khôi phục.
- Giữ bằng chứng lỗi đủ để phân tích sau khi ứng dụng được ổn định.

Không coi `removeTransformer` là thao tác gỡ cài đặt toàn bộ agent. Nó không tự hoàn tác bytecode đã sửa, đóng mọi luồng, dỡ thư viện native hay xóa mọi trạng thái. Khởi động lại JVM theo cấu hình đã biết thường là ranh giới rõ ràng hơn cho phục hồi agent, nhưng vẫn phải thử quy trình đó với hệ thống cụ thể.

Một thay đổi phiên bản, cấu hình thu thập hoặc tập plugin có thể làm thay đổi kết luận kiểm chứng trước đó. Duy trì bản ghi theo artifact/cấu hình thay vì gắn nhãn “agent đáng tin mãi mãi” cho một tên sản phẩm.

## 9. Những kết luận không nên rút ra

| Bằng chứng đang có | Chưa thể kết luận |
| --- | --- |
| Hash khớp mốc từ nguồn đã xác minh | Agent không có lỗi hoặc không thu thập dữ liệu nhạy cảm |
| Chữ ký hợp lệ và người ký được chấp nhận | Mọi hành vi đều phù hợp ứng dụng |
| Có `Premain-Class` và class tương ứng | Điểm vào đúng chữ ký, tương thích mọi JVM |
| Chạy được một lần ở môi trường thử | Ổn định dưới tải dài hạn hoặc khi mất mạng |
| Agent không khai báo các khả năng tùy chọn | Agent bị cô lập và không thể tác động dữ liệu ứng dụng |
| Gỡ được transformer | Ứng dụng đã quay về toàn bộ trạng thái trước khi dùng agent |

Tự thực hành:

1. Với một agent bạn dự định dùng, lập bản ghi nguồn, phiên bản, hash, cấu hình và các thành phần phụ.
2. Chỉ ra nguồn đáng tin của checksum/người ký; phân biệt việc xác thực nguồn gốc với kiểm tra mã có lỗi hay không.
3. Thiết kế một phép thử đích thu thập không phản hồi và nêu dữ liệu cần quan sát.
4. Nêu bằng chứng còn thiếu trước khi chuyển từ kết quả `staticChecks=passed` sang quyết định triển khai.
