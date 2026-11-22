# Maven Wrapper: mục đích và quan hệ với bản Maven cài trên máy

## 1. Maven Wrapper giải quyết vấn đề gì?

Trong dự án Java dùng Maven, lệnh `mvn` thường trỏ đến bản **Apache Maven được cài trên máy và tìm thấy qua PATH**. Hai lập trình viên có thể cài hai phiên bản Maven khác nhau; máy CI cũng có thể có phiên bản thứ ba. Điều này gây khác biệt khi Maven, plugin hoặc cấu hình dự án yêu cầu hành vi cụ thể của một phiên bản.

**Maven Wrapper** là bộ script đi kèm mã nguồn dự án: `mvnw` cho Linux/macOS và `mvnw.cmd` cho Windows. Thay vì phụ thuộc vào bản Maven có sẵn trong PATH, các script dùng **phiên bản Maven do dự án chỉ định** trong `.mvn/wrapper/maven-wrapper.properties`. Nếu bản phân phối đó chưa có trong bộ nhớ đệm của Wrapper, script sẽ tải và giải nén trước khi thực thi các goal Maven được truyền vào.

Vì thế, khi một dự án đã có Wrapper, người mới clone dự án có thể chạy build mà **không cần cài Maven toàn hệ thống**. Vẫn cần môi trường Java phù hợp với Maven và dự án, cùng công cụ tải xuống/kết nối mạng ở lần khởi tạo nếu chưa có bản phân phối trong cache.

## 2. `mvn` khác `mvnw` thế nào?

| Khía cạnh | `mvn` | `./mvnw` hoặc `mvnw.cmd` |
| --- | --- | --- |
| Lệnh lấy Maven từ đâu? | Bản Maven đã cài, được shell tìm qua PATH. | Bản Maven được cấu hình bởi Wrapper của **dự án hiện tại**. |
| Máy phải cài Maven trước không? | Có, để gọi được `mvn`. | Không, nếu dự án đã có đầy đủ file Wrapper và môi trường tải/chạy đáp ứng. |
| Phiên bản được chọn theo đâu? | Bản cài đang được gọi từ PATH. | Thuộc tính `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties`. |
| Tự tải bản Maven cần dùng? | Thông thường không. | Có, khi bản phân phối cấu hình chưa được cache. |
| Goal và pha build? | `mvn clean verify`. | `./mvnw clean verify` chạy cùng các goal `clean` và `verify`. |
| Ảnh hưởng đến bản Maven cài máy? | Dùng trực tiếp bản đó. | Không nâng cấp, gỡ bỏ hoặc thay thế Maven trong PATH. |

**Tình huống cụ thể:** máy A cài Maven 3.8.x, máy B cài Maven 3.9.x; dự án cấu hình Wrapper tải Maven 3.9.9 (phiên bản ví dụ). Khi dùng `mvn -version`, hai máy có thể hiển thị hai phiên bản khác nhau. Khi đứng tại gốc dự án và dùng `./mvnw -version` (hoặc `.\mvnw.cmd -version` trên Windows), cả hai hướng tới Maven 3.9.9 sau khi Wrapper chuẩn bị bản phân phối đó. Phiên bản Java, hệ điều hành và các yếu tố khác vẫn có thể khác nhau.

**Điểm dễ nhầm:** nếu máy đã cài đúng Maven 3.9.9, Wrapper **không mặc nhiên dùng lại thư mục cài đặt toàn hệ thống đó**. Nó quản lý bản phân phối riêng theo cấu hình và cache của Wrapper.

## 3. Các file của Wrapper nằm ở đâu?

Ví dụ cấu trúc dự án sau khi khởi tạo Wrapper loại `only-script`:

```text
my-app/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    └── ...
```

- `mvnw`: script cho shell trên Linux/macOS.
- `mvnw.cmd`: script cho Windows.
- `.mvn/wrapper/maven-wrapper.properties`: khai báo URL bản phân phối Maven và các thuộc tính liên quan.
- `pom.xml`: vẫn là cấu hình dự án Maven (dependencies, plugins, modules...). Wrapper không thay thế `pom.xml`.

Các file bổ sung **phụ thuộc loại Wrapper**. Chẳng hạn `bin` có thể chứa `.mvn/wrapper/maven-wrapper.jar`; `source` có thể chứa `.mvn/wrapper/MavenWrapperDownloader.java`. Với `only-script` (mặc định của Apache Maven Wrapper Plugin hiện hành), không cần hai file đó.

Khi làm việc nhóm, nên đưa các script và file properties vào Git. Với `bin`, đưa cả JAR của Wrapper vào Git nếu lựa chọn phân phối đó yêu cầu. Nếu thiếu file Wrapper, máy mới clone có thể không chạy được `mvnw`.

## 4. Wrapper chọn và chạy phiên bản Maven như thế nào?

Luồng cơ bản khi chạy `./mvnw clean verify`:

1. Script Wrapper tại gốc dự án đọc `.mvn/wrapper/maven-wrapper.properties`.
2. Wrapper xác định `distributionUrl` — URL của bản phân phối Maven được yêu cầu.
3. Nếu bản Maven đó chưa được chuẩn bị trong cache, Wrapper tải và giải nén. Theo cấu hình thông thường, bản phân phối nằm dưới `~/.m2/wrapper/dists`; vị trí có thể thay đổi theo cấu hình môi trường.
4. Wrapper gọi Maven từ bản phân phối vừa chọn, truyền tiếp các tham số `clean verify`.
5. Maven đọc `pom.xml`, giải quyết plugin/dependency và thực hiện lifecycle như một lần chạy Maven thông thường.

Ví dụ nội dung chính của `.mvn/wrapper/maven-wrapper.properties`:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Đây là **đường dẫn minh họa cho Maven 3.9.9**, không có nghĩa 3.9.9 là bản mới nhất. Thông thường, nhóm chọn bản Maven phù hợp dự án, kiểm tra URL chính thức rồi đưa thay đổi vào Git.

Có hai vị trí cache dễ bị lẫn:

- `~/.m2/wrapper/dists`: nơi Wrapper lưu các bản **phân phối Maven** đã tải.
- `~/.m2/repository`: kho cục bộ dành cho **dependency/plugin artifact** mà Maven sử dụng.

Có Maven trong cache Wrapper không có nghĩa mọi thư viện đã có trong repository cục bộ. Một build có thể vẫn cần mạng để tải dependency hoặc plugin.

## 5. Tạo Wrapper cho một dự án hiện có

Ở giai đoạn **tạo Wrapper lần đầu**, người thiết lập cần có Maven chạy được lệnh `mvn` để gọi Maven Wrapper Plugin. Từ thư mục gốc có `pom.xml`, chạy:

```bash
mvn -N wrapper:wrapper -Dmaven=3.9.9
```

Giải thích:

- `-N` / `--non-recursive`: thực thi goal tại project gốc, không đi vào từng module con; hữu ích với dự án nhiều module.
- `wrapper:wrapper`: goal của Apache Maven Wrapper Plugin, sinh hoặc cập nhật các file Wrapper.
- `-Dmaven=3.9.9`: yêu cầu Wrapper sử dụng Maven 3.9.9; **khác** với phiên bản Maven đang chạy lệnh khởi tạo.
- Nếu bỏ `-Dmaven`, plugin thường lấy phiên bản Maven đang thực thi goal làm mặc định. Vì thế, hãy chỉ định phiên bản một cách có chủ đích.

Có thể ghi rõ phiên bản plugin để việc khởi tạo dễ kiểm soát, ví dụ:

```bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
```

Lệnh thứ hai yêu cầu Maven Wrapper Plugin 3.3.4, tạo Wrapper loại `only-script` và chọn Maven 3.9.9. **Phiên bản của Wrapper Plugin (3.3.4) khác với phiên bản Maven được Wrapper tải/chạy (3.9.9)**.

Sau đó kiểm tra và commit `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties` (và file bổ sung nếu loại Wrapper đã chọn cần). Trên Linux/macOS, nếu script thiếu quyền thực thi, chạy `chmod +x mvnw` và bảo đảm Git lưu executable bit.

## 6. Dùng Wrapper khi clone, phát triển và chạy CI

Trong thư mục gốc dự án đã có Wrapper:

**Linux/macOS (shell):**

```bash
./mvnw -version
./mvnw clean verify
```

**Windows PowerShell:**

```powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
```

Lệnh `-version` là cách kiểm tra Maven nào thực sự được chạy. Với cấu hình ví dụ ở trên, thông tin phiên bản Maven được kỳ vọng là `3.9.9`; các dòng chi tiết về Java, hệ điều hành và đường dẫn có thể khác nhau giữa máy. Hãy so sánh với `mvn -version` nếu muốn thấy sự khác biệt giữa bản Maven toàn hệ thống và bản Maven do Wrapper chọn.

Trong CI chạy trên Linux, có thể dùng:

```bash
./mvnw -B -ntp verify
```

Trong đó `-B` bật chế độ batch cho CI, `-ntp` giảm hiển thị tiến độ tải xuống. CI cần cung cấp JDK và kết nối/đường cache phù hợp. Dùng lệnh Wrapper rõ ràng trong pipeline cũng giúp tránh việc CI vô tình chạy bản Maven đã cài sẵn.

Một quy trình làm việc nhóm hợp lý:

1. Người duy trì dự án chọn phiên bản Maven, tạo Wrapper và commit các file.
2. Thành viên mới clone repo, chuẩn bị JDK, chạy script Wrapper tương ứng hệ điều hành.
3. CI cũng gọi Wrapper từ repo.
4. Khi cần nâng Maven, nhóm thay đổi phiên bản Wrapper một cách có kiểm soát, kiểm thử build, rồi commit bản cập nhật.

## 7. Các loại Maven Wrapper và ý nghĩa thực tế

Apache Maven Wrapper Plugin hỗ trợ một số cách khởi động:

| Loại | Cơ chế chính | Khi nào đáng cân nhắc |
| --- | --- | --- |
| `only-script` | Script tự tải bản phân phối Maven bằng công cụ của hệ điều hành; không dùng `maven-wrapper.jar`. | Mặc định gọn nhẹ cho dự án mới; cần công cụ tải phù hợp ở lần đầu. |
| `script` | Script tải JAR hỗ trợ Wrapper nếu cần, rồi dùng JAR để chuẩn bị Maven. | Muốn dùng cơ chế Wrapper qua JAR mà không commit sẵn binary. |
| `bin` | Có sẵn `maven-wrapper.jar` trong repo. | Muốn tránh bước tải riêng JAR của Wrapper, chấp nhận quản lý file nhị phân. |
| `source` | Có nguồn Java hỗ trợ tải JAR của Wrapper. | Cần phương án tải JAR qua mã nguồn Java trong một số môi trường. |

Không nên kết luận rằng mọi dự án có Wrapper đều phải có `maven-wrapper.jar`. Kiểm tra loại Wrapper đang dùng và cấu trúc file thực tế. Để chủ động chọn loại khi tạo/cập nhật, dùng `-Dtype=only-script`, `-Dtype=script`, `-Dtype=bin` hoặc `-Dtype=source`.

## 8. Wrapper đảm bảo điều gì, và chưa đảm bảo điều gì?

Wrapper **giúp thống nhất phiên bản Maven được thực thi**. Tuy nhiên, để build có tính lặp lại, cần kiểm soát thêm:

- **JDK:** Wrapper không tự khóa hoặc cài Java. Phiên bản Java đang dùng thường phụ thuộc `JAVA_HOME`, môi trường chạy và cấu hình công cụ. Dự án có thể dùng Maven Enforcer, Maven Toolchains hoặc cấu hình CI để ràng buộc JDK.
- **Dependencies và plugins:** khai báo và phiên bản thuộc `pom.xml`, parent POM, BOM, repository và cấu hình liên quan. Tránh phiên bản động/snapshot không được kiểm soát khi muốn build ổn định.
- **Môi trường tải:** lần đầu có thể cần Internet hoặc proxy/repository nội bộ; về sau vẫn có thể cần tải dependency/plugin. Cache có sẵn không bảo đảm hoàn toàn offline.
- **Cấu hình người dùng:** `settings.xml`, mirror, proxy, credential và các thiết lập Maven khác vẫn có thể ảnh hưởng đến build.
- **IDE:** IDE có thể dùng bản Maven riêng nếu chưa cấu hình theo Wrapper. Kiểm tra phần Maven settings của IDE và đối chiếu với lệnh CLI.

Để tăng độ tin cậy khi tải, Maven Wrapper hỗ trợ thuộc tính `distributionSha256Sum` (và `wrapperSha256Sum` khi áp dụng cho JAR Wrapper). Chỉ điền checksum SHA-256 đã xác minh từ nguồn tin cậy; không ghi checksum minh họa hoặc đoán giá trị. Với hạ tầng doanh nghiệp, có thể cấu hình URL tải phù hợp với repository/mirror được phép sử dụng.

## 9. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `mvn` chạy được nhưng `./mvnw` báo không tìm thấy file | Đang đứng sai thư mục hoặc repo chưa có script. | Vào đúng gốc dự án, kiểm tra file Wrapper đã được commit/clone. |
| `./mvnw: Permission denied` trên Linux/macOS | Script chưa có quyền thực thi. | `chmod +x mvnw`; lưu executable bit trong Git. |
| `mvn` và `./mvnw` hiển thị phiên bản khác nhau | Hai lệnh chọn Maven từ hai nguồn khác nhau. | Kiểm tra `mvn -version`, `./mvnw -version` và `distributionUrl`; đây có thể là hành vi đúng. |
| Wrapper lỗi khi tải Maven | URL sai, máy mất mạng, proxy/TLS bị chặn hoặc nguồn tải không truy cập được. | Kiểm tra `distributionUrl`, kết nối và cấu hình proxy/repository của môi trường. |
| Wrapper tìm được Maven nhưng build vẫn lỗi | JDK không tương thích, plugin/dependency lỗi, repository chưa truy cập được hoặc lỗi mã nguồn. | Xem log Maven và `java -version`; phân biệt lỗi khởi động Wrapper với lỗi build của dự án. |
| Chạy offline ngay sau clone thất bại | Maven distribution hoặc artifact chưa có trong cache. | Chuẩn bị cache phù hợp trước khi chạy offline; không giả định Wrapper đã tải mọi thứ. |

Khi cần chẩn đoán rõ hơn, có thể bật biến môi trường `MVNW_VERBOSE=true` theo hướng dẫn của Apache Maven Wrapper. Tránh đưa mật khẩu proxy/repository vào file được commit; dùng cơ chế quản lý secret của môi trường.

## 10. Tự kiểm tra hiểu bài

1. Dự án dùng `distributionUrl` cho Maven 3.9.9, máy cài Maven 3.8.x. Chạy `mvn verify` dùng bản nào? **Bản Maven mà shell tìm thấy qua PATH (giả sử là 3.8.x)**. Chạy `./mvnw verify` dùng bản nào? **3.9.9 theo Wrapper**.
2. Xóa bản Maven cài toàn hệ thống rồi clone một dự án đã commit đầy đủ Wrapper: còn build được không? **Có thể**, nếu JDK và các điều kiện tải/chạy đáp ứng; chạy script `mvnw` hoặc `mvnw.cmd`.
3. Chỉ commit `pom.xml` mà không commit `mvnw`, `mvnw.cmd` và properties: người mới có tự dùng Wrapper được không? **Không thể gọi Wrapper từ những file chưa có**.
4. Wrapper pin Maven 3.9.9 có nghĩa mọi máy sẽ dùng cùng JDK và cùng bytecode đầu ra không? **Không**. Wrapper chỉ giải quyết phần phiên bản Maven; JDK, dependency, plugin và môi trường build còn cần quản lý riêng.

## Tài liệu chính thức

- [Apache Maven Wrapper — tổng quan, cách dùng, thay đổi phiên bản, checksum](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — Usage và các kiểu phân phối](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Apache Maven Wrapper Plugin — tham số của goal wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
