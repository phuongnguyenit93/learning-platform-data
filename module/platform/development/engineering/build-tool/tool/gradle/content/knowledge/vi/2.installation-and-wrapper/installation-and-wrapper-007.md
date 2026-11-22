# Kiểm tra checksum bản phân phối và tính toàn vẹn Gradle Wrapper

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể: (1) phân biệt tính toàn vẹn của bản phân phối Gradle với tính toàn vẹn của mã khởi chạy Wrapper; (2) ghim checksum SHA-256 của tệp ZIP trong `gradle-wrapper.properties`; (3) tự kiểm tra `gradle-wrapper.jar` trước khi tin tưởng thực thi; (4) đưa việc kiểm tra vào quy trình review và CI; (5) xử lý tình huống checksum không khớp mà không vô hiệu hóa cơ chế bảo vệ.

Bài học thuộc chủ đề **Cài đặt và Wrapper** của **Build Tool Gradle**. Các lệnh minh họa dùng Gradle **9.8.2** chỉ để có một ví dụ thống nhất, với checksum công bố thực tế; dự án đang dùng phiên bản khác phải lấy đúng checksum cho **phiên bản và loại ZIP** mà dự án khai báo. Không cần nâng cấp Gradle chỉ để thực hành kiểm tra.

## 2. Hai thành phần khác nhau phải được xác minh

Một dự án dùng Gradle Wrapper thường commit bốn tệp:

```text
gradlew                              # Script cho Linux/macOS
gradlew.bat                          # Script cho Windows
gradle/wrapper/gradle-wrapper.jar    # Mã Java khởi chạy Wrapper
gradle/wrapper/gradle-wrapper.properties  # URL, phiên bản và tùy chọn tải Gradle
```

Chuỗi thực thi về cơ bản là:

```text
Developer/CI chạy ./gradlew
       |
       v
gradlew -> gradle-wrapper.jar
       |
       v
Đọc gradle-wrapper.properties
       |
       v
Tải gradle-<version>-bin.zip (nếu chưa có bản phân phối hợp lệ trong cache)
       |
       v
Đối chiếu SHA-256 của ZIP với distributionSha256Sum (nếu được cấu hình)
       |
       v
Giải nén/chạy Gradle -> cấu hình và thực thi build
```

| Đối tượng | Nằm ở đâu | Cách xác minh | Rủi ro nếu bỏ qua |
| --- | --- | --- | --- |
| Bản phân phối Gradle (ZIP) | Được tải từ `distributionUrl`, thường cache dưới `GRADLE_USER_HOME/wrapper/dists` | Ghim `distributionSha256Sum` | ZIP bị thay đổi/hỏng nhưng vẫn được sử dụng |
| Wrapper JAR | `gradle/wrapper/gradle-wrapper.jar` trong repository | So SHA-256 của JAR với checksum do Gradle công bố hoặc dùng CI validation | Mã JAR lạ có thể chạy **trước** khi cơ chế kiểm tra ZIP phát huy tác dụng |
| Script và cấu hình Wrapper | `gradlew`, `gradlew.bat`, `gradle-wrapper.properties` | Review diff, nguồn phát hành, URL và hash trong PR | Script/URL/hash bị sửa đồng thời, chuyển hướng luồng tin cậy |

**Điểm cốt lõi:** `distributionSha256Sum` xác minh **ZIP được tải về**, không kiểm tra `gradle-wrapper.jar`, script khởi chạy hay mã build. Bản thân JAR cũng không tự chứng minh rằng nó đáng tin.

## 3. Kiểm tra checksum SHA-256 của bản phân phối

### 3.1. Nguồn checksum đáng tin

Trước tiên, đọc `distributionUrl` trong `gradle/wrapper/gradle-wrapper.properties`. Từ URL, xác định **chính xác phiên bản** và loại bản phân phối `-bin` hay `-all`. Sau đó đối chiếu SHA-256 với trang chính thức:

- Danh mục checksum: https://gradle.org/release-checksums/
- Tệp checksum đi kèm ZIP: `https://services.gradle.org/distributions/gradle-<version>-bin.zip.sha256` (đổi `-bin` thành `-all` nếu phù hợp).

`-bin` và `-all` **không có cùng checksum**. Không dùng mã hash của một phiên bản cho phiên bản khác; không sao chép hash không rõ nguồn hoặc hash nằm ngay trên máy chủ không đáng tin mà bạn đang điều tra. SHA-256 chỉ có ý nghĩa bảo mật khi giá trị kỳ vọng được lấy/xác nhận từ nguồn đáng tin.

### 3.2. Ghim checksum trong properties

Ví dụ về những dòng có liên quan trong `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.8.2-bin.zip
distributionSha256Sum=21bd5da2de49b642904077f38c0efdc7778e92b3ed0889392dca61b97e389607
```

Đây là checksum **của ZIP 9.8.2-bin** được Gradle công bố; các thuộc tính Wrapper khác của dự án vẫn được giữ nguyên. Trường `distributionUrl` thường viết `https\://` trong tệp Java properties do dấu `:` được escape. `distributionSha256Sum` là chuỗi 64 ký tự hex; đây không phải mật khẩu hay chữ ký số.

Có thể cập nhật Wrapper trong một repository đã được tin cậy bằng lệnh tương ứng của `wrapper` task:

```bash
gradle wrapper --gradle-version 9.8.2 --distribution-type bin \
  --gradle-distribution-sha256-sum 21bd5da2de49b642904077f38c0efdc7778e92b3ed0889392dca61b97e389607
```

Lệnh trên dùng một bản cài `gradle` đã được tin cậy để tạo/cập nhật cấu hình. Nếu chỉ thay phiên bản phân phối, JAR Wrapper có thể vẫn thuộc phiên bản Gradle dùng để chạy task; quy trình nâng cấp đầy đủ có thể cần chạy `wrapper` task lần nữa bằng bản Gradle mới **sau khi đã xác minh thành phần khởi chạy**. Sau nâng cấp phải kiểm tra lại JAR, script, URL và checksum, thay vì giả định tất cả tự đồng bộ.

### 3.3. Khi nào Gradle tự đối chiếu?

Nếu `distributionSha256Sum` được cấu hình, Wrapper so SHA-256 của tệp ZIP **khi tải bản phân phối mới**. Nếu khác nhau, nó báo lỗi xác minh và không tiếp tục dùng ZIP vừa tải. Khi bản phân phối đã có trong cache và được đánh dấu hợp lệ, những lần chạy tiếp theo **không nhất thiết tải lại hoặc tính lại checksum**. Việc thêm hash hôm nay vì thế không chứng minh các bản Gradle đã tồn tại trong cache trước đó từng được kiểm tra.

Để quan sát lần tải/xác minh mới mà không xóa cache đang dùng, có thể đặt thư mục Gradle user home tạm thời. Ví dụ Linux/macOS, chỉ chạy **sau** khi đã xác minh script/JAR của dự án:

```bash
tmp_gradle_home="$(mktemp -d)"
GRADLE_USER_HOME="$tmp_gradle_home" ./gradlew --version
rm -rf "$tmp_gradle_home"
```

Dòng đầu tạo cache riêng; dòng thứ hai buộc Wrapper tải phân phối vào cache đó và đối chiếu checksum đã ghim; dòng cuối xóa **đúng thư mục tạm vừa tạo** sau khi chạy xong. Nếu lệnh trước gặp lỗi, hãy dọn thư mục tạm khi đã kiểm tra đường dẫn. Việc tải có thể cần mạng. Không kiểm tra dự án chưa tin cậy bằng cách chạy `./gradlew` trước bước xác minh.

### 3.4. Kiểm tra thủ công ZIP đã tải

Khi có một ZIP cụ thể để điều tra, tính hash trên **các byte của chính ZIP đó**:

```bash
sha256sum gradle-9.8.2-bin.zip             # Linux
shasum -a 256 gradle-9.8.2-bin.zip        # macOS
```

```powershell
(Get-FileHash .\gradle-9.8.2-bin.zip -Algorithm SHA256).Hash.ToLowerInvariant()
```

Với ZIP chính thức đúng ví dụ, digest phải là `21bd5da2de49b642904077f38c0efdc7778e92b3ed0889392dca61b97e389607`. Hash khác nghĩa là tệp không khớp với bản đã ghim; **dừng sử dụng và tìm nguyên nhân**, không tự sửa giá trị kỳ vọng theo tệp lạ.

## 4. Kiểm tra tính toàn vẹn của gradle-wrapper.jar

### 4.1. Tại sao JAR cần kiểm tra độc lập?

`gradle-wrapper.jar` là binary trong repository, chạy trước khi Gradle tải phân phối và trước nhiều kiểm soát của build. Một PR độc hại có thể thay tệp này ngay cả khi `distributionUrl` và `distributionSha256Sum` vẫn đúng. Vì vậy, **hash của ZIP khớp không suy ra JAR an toàn**.

Gradle công bố checksum SHA-256 của Wrapper JAR tại https://gradle.org/release-checksums/. Hãy đối chiếu với bản chính thức phù hợp. Nếu JAR được tạo bởi bản Gradle khác với phiên bản đích trong `distributionUrl`, cần xác định nguồn tạo JAR trước khi kết luận có xâm phạm. Một số bản phát hành có thể có JAR giống nhau và cùng hash. Với các phiên bản Gradle cũ 3.3–4.0.2, không có cùng bảo đảm về JAR tái lập như những bản hiện đại; cần thận trọng hơn.

### 4.2. Linux: so hash với checksum phát hành

Ví dụ này giả định Wrapper JAR đã được cập nhật từ bản phát hành **9.8.2**. Chạy ở thư mục gốc dự án:

```bash
expected="$(curl -fsSL https://services.gradle.org/distributions/gradle-9.8.2-wrapper.jar.sha256 | tr -d '[:space:]')"
actual="$(sha256sum gradle/wrapper/gradle-wrapper.jar | awk '{print $1}')"

if [ "$actual" = "$expected" ]; then
  printf 'Wrapper JAR: OK\n'
else
  printf 'Wrapper JAR: CHECKSUM MISMATCH\n' >&2
  exit 1
fi
```

Nếu JAR hợp lệ, output do đoạn script tự in:

```text
Wrapper JAR: OK
```

Đây là kết quả **có điều kiện khi hai giá trị bằng nhau**, không phải output được bảo đảm cho mọi repository. Trên macOS, thay `sha256sum gradle/wrapper/gradle-wrapper.jar` bằng `shasum -a 256 gradle/wrapper/gradle-wrapper.jar`; phần còn lại tương đương.

### 4.3. Windows PowerShell: so hash với checksum phát hành

Chạy ở thư mục gốc dự án:

```powershell
$expected = [string](Invoke-RestMethod -Uri 'https://services.gradle.org/distributions/gradle-9.8.2-wrapper.jar.sha256')
$actual = (Get-FileHash '.\gradle\wrapper\gradle-wrapper.jar' -Algorithm SHA256).Hash

if ($actual.ToLowerInvariant() -ne $expected.Trim().ToLowerInvariant()) {
    throw 'Wrapper JAR: CHECKSUM MISMATCH'
}
'Wrapper JAR: OK'
```

Hash Wrapper JAR 9.8.2 được Gradle liệt kê là `3b8a25775a69158b5ad2b1d17a80a88dc7b40a352a73eb27d06c612a7ce68e98`. Bạn cũng có thể tính hash của file trên máy rồi tra mục **Wrapper JAR Checksum** trong danh mục chính thức; không nhầm với mục **Binary-only ZIP Checksum** hoặc **Complete ZIP Checksum**.

Nếu JAR thuộc một bản phát hành hợp lệ khác, việc so với đúng riêng 9.8.2 có thể báo mismatch dù binary vẫn là Gradle chính thức. Kiểm tra hash trong danh mục tất cả phiên bản, xác định phiên bản tạo JAR, rồi tái tạo/cập nhật Wrapper bằng nguồn tin cậy nếu cần. Nếu hash **không có trong danh mục tương ứng** hoặc nguồn gốc không giải thích được, coi JAR là chưa được xác minh và không chạy nó.

## 5. Kiểm tra script, URL và thay đổi trong Git

Checksum Wrapper JAR và ZIP không bao phủ `gradlew`, `gradlew.bat`, `gradle-wrapper.properties` hay logic build. Khi nhận PR, trước khi thực thi Wrapper:

1. Xem thay đổi ở cả bốn tệp Wrapper và lý do nâng cấp; xem binary JAR có bị thay thế bất ngờ không.
2. Xác nhận `distributionUrl` trỏ đúng phiên bản/loại phân phối và nguồn được tổ chức cho phép, ưu tiên HTTPS.
3. So `distributionSha256Sum` với nguồn phát hành đáng tin **riêng biệt**; tránh chấp nhận một PR đồng thời thay URL và giá trị hash mà không kiểm chứng.
4. Kiểm tra `gradle-wrapper.jar` bằng checksum phát hành hay bước CI chuyên dụng.
5. Review script khởi chạy; nếu script bị sửa khác với output Wrapper task chính thức thì cần giải thích rõ.
6. Chỉ sau các bước trên mới dùng `./gradlew` hoặc `gradlew.bat` để chạy Gradle.

Lệnh hỗ trợ review tại repository đã checkout:

```bash
git diff -- gradlew gradlew.bat gradle/wrapper/gradle-wrapper.properties
git diff --stat -- gradle/wrapper/gradle-wrapper.jar
```

`git diff --stat` chỉ cho biết JAR thay đổi; **không thể xác minh nội dung binary**. Với PR, nên xem diff so với nhánh gốc phù hợp, không chỉ so với working tree hiện tại. SHA-256 chứng minh file trùng với một artifact tham chiếu tin cậy; nó không tự chứng minh code bên trong không có lỗ hổng hoặc build script an toàn.

## 6. Tự động kiểm tra trong CI

Với GitHub Actions, `gradle/actions/setup-gradle@v4` có kiểm tra Wrapper JAR tích hợp; khi gặp JAR không nằm trong danh sách hợp lệ, hành động có thể chặn job sớm. Ví dụ tối giản:

```yaml
name: Verify Gradle Wrapper
on: [pull_request, push]

jobs:
  verify-wrapper:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: gradle/actions/setup-gradle@v4
      - name: Confirm Gradle starts with pinned distribution
        run: ./gradlew --version
```

Bước `setup-gradle` giúp xác thực JAR; bước `./gradlew --version` kiểm tra luồng khởi chạy và bản phân phối theo cấu hình khi cần tải. Pipeline phải chứa `distributionSha256Sum` hợp lệ để xác minh ZIP; **chỉ dùng action kiểm tra JAR không tự bổ sung hash cho ZIP**. Với môi trường CI không dùng GitHub Actions, tạo bước kiểm tra SHA-256 của JAR trước khi chạy `gradlew`, đồng thời bắt buộc cấu hình hash cho distribution. Với CI đã có cache, cần nhớ việc tải từ cache không tương đương kiểm tra lại ZIP ở mọi lần chạy.

Mẫu trên tập trung vào Wrapper. Ở dự án thực tế, review quyền của workflow/action, script và build logic theo chính sách bảo mật của tổ chức.

## 7. Khi checksum không khớp: cách xử lý

| Hiện tượng | Nguyên nhân cần điều tra | Hướng xử lý đúng |
| --- | --- | --- |
| Wrapper báo `Verification of Gradle distribution failed` | ZIP bị lỗi/bị thay đổi; sai checksum của version hoặc nhầm `-bin`/`-all` | Đối chiếu URL + checksum chính thức, tìm lỗi đường truyền/mirror, tải lại từ nguồn tin cậy |
| Mới thêm `distributionSha256Sum` nhưng build dùng cache cũ | Wrapper chỉ kiểm tra khi tải phân phối mới | Dùng cache độc lập để thực hành xác minh tải mới; không coi cache cũ là đã được xác minh |
| Checksum `gradle-wrapper.jar` không khớp với phiên bản đang khai báo | JAR có thể chưa được tái tạo sau lần nâng cấp, hoặc binary bị sửa | Tra hash thực tế trong danh mục Gradle; nếu không giải thích được thì cô lập, tái tạo từ nguồn đã tin cậy |
| CI chặn Wrapper JAR | JAR không được nhận diện là artifact hợp lệ, hoặc dùng bản thử nghiệm/legacy | Xác minh nguồn và checksum; nâng cấp hoặc cấu hình theo tài liệu action sau khi chứng minh nguồn gốc |
| PR vừa sửa `distributionUrl` vừa sửa `distributionSha256Sum` | Có thể là nâng cấp hợp lệ, cũng có thể thay nguồn tải | Review độc lập URL, version, ZIP hash, JAR hash và script |

**Không sửa `distributionSha256Sum` thành hash của ZIP chưa biết nguồn để “cho build chạy”. Không xóa thuộc tính hoặc tắt kiểm tra để bỏ qua mismatch.** Nếu nghi binary bị can thiệp, dừng chạy Wrapper trên repository đó; phục hồi file từ nguồn đã xác minh, kiểm tra lịch sử thay đổi và chạy lại kiểm tra trước khi tiếp tục.

## 8. Tình huống luyện tập và tự kiểm tra

Giả sử PR đổi `distributionUrl` từ `gradle-9.8.1-bin.zip` sang `gradle-9.8.2-bin.zip`, nhưng giữ nguyên `distributionSha256Sum` của 9.8.1.

- **Câu hỏi:** Khi nào lỗi xuất hiện và vì sao? **Đáp án:** Khi Wrapper tải ZIP 9.8.2 mới, SHA-256 của ZIP đó không bằng hash 9.8.1 đã ghim, nên xác minh thất bại. Nếu máy đã có cache hợp lệ, hành vi tải có thể khác; không dùng tình trạng cache làm bằng chứng cấu hình đúng.
- **Câu hỏi:** Chỉ sửa hash thành giá trị của ZIP mới đã đủ chưa? **Đáp án:** Chưa. Cần kiểm tra URL, phiên bản, script và checksum `gradle-wrapper.jar`, đặc biệt nếu binary thay đổi.
- **Câu hỏi:** Nếu ZIP hash khớp nhưng JAR hash lạ, có nên chạy `./gradlew test`? **Đáp án:** Chưa. Wrapper JAR chạy trước bước kiểm tra ZIP; cần xác minh/khôi phục JAR.
- **Câu hỏi:** Nếu cả ZIP và JAR hash khớp, build đã an toàn tuyệt đối chưa? **Đáp án:** Chưa. Plugin, dependency, script, repository và mã build vẫn cần kiểm soát riêng; checksum chỉ giải quyết tính toàn vẹn của những artifact được đối chiếu.

Tiêu chí hoàn thành bài: bạn có thể chỉ ra hai hash riêng biệt, giải thích tại sao cả hai quan trọng, tra đúng artifact chính thức, kiểm tra từ dòng lệnh và xác định hành động an toàn khi hai giá trị không khớp.

## 9. Tài liệu chính thức

- Gradle Wrapper (cấu trúc, checksum bản phân phối, xác minh JAR, nâng cấp): https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle Security Best Practices: https://docs.gradle.org/current/userguide/best_practices_security.html
- Gradle distribution & Wrapper JAR SHA-256 checksums: https://gradle.org/release-checksums/
- Gradle Securing the Build Tool (cơ chế kiểm tra, cache và mức độ tin cậy): https://docs.gradle.org/current/userguide/securing_build_tool.html