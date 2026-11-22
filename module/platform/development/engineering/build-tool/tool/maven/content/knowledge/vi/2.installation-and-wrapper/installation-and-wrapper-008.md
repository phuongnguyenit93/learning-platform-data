# Cố định bản phân phối Maven bằng maven-wrapper.properties

## 1. Mục tiêu: mọi người chạy đúng phiên bản Maven của dự án

Trong dự án Java, lệnh `mvn` thường sử dụng phiên bản Maven cài sẵn trên máy và được tìm thấy qua `PATH`. Hai lập trình viên hoặc một máy CI có thể dùng các phiên bản khác nhau, dẫn đến hành vi plugin, cách xử lý cấu hình hoặc kết quả build khác nhau. **Maven Wrapper** giải quyết phần quản lý phiên bản công cụ build: dự án cung cấp các script `mvnw` và `mvnw.cmd`, đọc cấu hình trong `.mvn/wrapper/maven-wrapper.properties`, tải (nếu cần) rồi chạy bản phân phối Maven đã chọn.

**Cố định (pin) bản phân phối** nghĩa là ghi **URL của đúng một phiên bản Maven cụ thể** vào thuộc tính `distributionUrl`, đưa cấu hình đó vào Git và yêu cầu cả máy phát triển lẫn CI gọi Wrapper. Sau đó việc nâng cấp Maven là một thay đổi mã nguồn có thể review, thay vì phụ thuộc vào phiên bản Maven tình cờ có trên máy.

Phân biệt ba thứ dễ nhầm:

| Thứ được quản lý | Nằm ở đâu hoặc xác định bằng gì? | Ý nghĩa |
| --- | --- | --- |
| **Phiên bản Maven dùng để build** | `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties` | Bản phân phối chứa Maven CLI và các thư viện Maven Core được tải/chạy. |
| **Phiên bản Maven Wrapper** | Các script/bộ khởi động Wrapper và metadata như `wrapperVersion` do plugin tạo | Công cụ hỗ trợ tìm, tải và khởi động Maven. Phiên bản Wrapper **khác** phiên bản Maven được tải. |
| **Phiên bản Java/JDK** | JDK cài trên máy, cấu hình IDE/CI, `JAVA_HOME` hoặc Toolchains | Java dùng để chạy Maven và/hoặc để biên dịch dự án; Wrapper Maven không tự cài JDK. |

Ví dụ: dự án dùng Maven Wrapper 3.3.4 để chạy **Maven 3.9.9**, trong khi CI thiết lập **JDK 17**. Ba số phiên bản này thuộc ba lớp khác nhau. Bài này dùng Maven 3.9.9 làm **phiên bản minh họa cố định**, không ngụ ý mọi dự án phải chọn phiên bản đó.

## 2. Vị trí tệp và cấu trúc chuẩn

Ở thư mục gốc dự án Maven (cùng cấp với `pom.xml`), một thiết lập Wrapper loại `only-script` thường có dạng:

~~~text
java-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    ├── main/
    └── test/
~~~

- `mvnw`: script dành cho Linux/macOS và môi trường shell tương thích.
- `mvnw.cmd`: script cho Windows.
- `.mvn/wrapper/maven-wrapper.properties`: cấu hình cách Wrapper lấy bản phân phối Maven.
- `pom.xml`: cấu hình dự án, dependencies, plugins và quy trình build; **không phải** nơi chính để chọn bản phân phối Maven mà Wrapper tải.

Với một Wrapper đã tạo bằng Apache Maven Wrapper Plugin 3.3.4 ở chế độ `only-script`, ví dụ cấu hình hoàn chỉnh cho phần cố định phiên bản là:

~~~properties
wrapperVersion=3.3.4
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

Ba dòng có nhiệm vụ khác nhau:

1. `wrapperVersion=3.3.4` nhận diện phiên bản Wrapper được tạo. Nó **không** bảo Maven chạy phiên bản 3.3.4.
2. `distributionType=only-script` ghi nhận kiểu bộ khởi động: script tải bản Maven trực tiếp, không cần `maven-wrapper.jar`. Đây là một kiểu phân phối Wrapper; nó không quyết định phiên bản Maven.
3. **`distributionUrl=.../3.9.9/apache-maven-3.9.9-bin.zip` là dòng quyết định Maven 3.9.9**. Cả phần đường dẫn phiên bản và tên archive phải nhất quán. Đây là URL tới archive của một bản phát hành cụ thể, không phải URL tới một trang giới thiệu hay tới `maven-metadata.xml`.

Mẫu URL ở trên trỏ tới Maven Central qua HTTPS. Có thể thay bằng kho artifact nội bộ đáng tin cậy nếu tổ chức yêu cầu. Điều kiện cốt lõi vẫn là **archive Maven cụ thể, có phiên bản được xác định và có thể truy xuất**.

Một số bản Wrapper có thêm các thuộc tính liên quan đến nơi lưu file tải xuống, ví dụ `distributionBase`, `distributionPath`, `zipStoreBase` và `zipStorePath`. Chúng điều khiển vị trí cache/tệp phân phối, **không thay thế `distributionUrl`**. Không cần tự thêm chúng để làm công việc cố định phiên bản.

## 3. Tạo Wrapper và cố định bản phân phối lần đầu

### Bước 1. Chuẩn bị đúng ngữ cảnh

Mở terminal ở thư mục gốc có `pom.xml` hợp lệ. Cần cài **JDK** và, riêng cho lần khởi tạo Wrapper, có một bản Maven chạy được qua lệnh `mvn`. Sau khi Wrapper và cấu hình đã được đưa vào repository, người khác có thể dùng `mvnw` mà không cần cài Maven toàn cục.

Kiểm tra môi trường tạo Wrapper:

~~~bash
java -version
mvn -version
~~~

Nếu máy chưa nhận `java` hoặc `mvn`, cần cấu hình JDK/Maven cho bước khởi tạo. Đừng nhầm lỗi thiếu Java với lỗi của thuộc tính `distributionUrl`.

### Bước 2. Sinh script và cấu hình bằng plugin chính thức

Ví dụ dưới đây **cố định phiên bản Maven Wrapper Plugin** và yêu cầu nó sinh cấu hình cho Maven 3.9.9, loại `only-script`:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Giải thích:

- `-N` chạy mục tiêu tại dự án hiện tại mà không đệ quy xuống các module con; thích hợp khi chuẩn bị Wrapper ở thư mục gốc dự án đa module.
- `org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper` chỉ rõ plugin và goal tạo Wrapper, tránh phụ thuộc vào phiên bản plugin được suy ra từ prefix.
- `-Dmaven=3.9.9` yêu cầu bản phân phối Maven 3.9.9.
- `-Dtype=only-script` chọn cách triển khai chỉ dùng các script `mvnw`/`mvnw.cmd`, không cần commit Wrapper JAR.

Sau khi chạy thành công, kiểm tra ba tệp `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`. Đọc dòng `distributionUrl` mà plugin tạo; giá trị cần chứa chính xác `/3.9.9/apache-maven-3.9.9-bin.zip`. Nếu dự án đã có Wrapper, hãy review `git diff` vì việc chạy lại goal có thể cập nhật nhiều tệp Wrapper, kể cả script và metadata.

Không chỉ tạo mỗi `maven-wrapper.properties` bằng tay cho một dự án chưa có Wrapper: còn cần các script tương ứng. Khi Wrapper đã tồn tại và đang hoạt động, bạn có thể chỉnh URL trong tệp properties để thay phiên bản Maven mà không nhất thiết phải sinh lại script.

### Bước 3. Commit cấu hình để cả nhóm dùng

Với loại `only-script`, những tệp quan trọng cần đưa vào Git là:

~~~bash
git add mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties
git diff --cached
git commit -m "Pin Maven distribution to 3.9.9"
~~~

Trên Linux/macOS, đảm bảo `mvnw` có quyền thực thi được theo dõi bởi Git. Nếu cần sửa quyền:

~~~bash
chmod +x mvnw
git add mvnw
~~~

Một số loại Wrapper khác dùng thêm `.mvn/wrapper/maven-wrapper.jar` hoặc `.mvn/wrapper/MavenWrapperDownloader.java`; danh sách tệp cần commit phải theo **loại Wrapper thực sự sử dụng**. Tránh quy tắc `.gitignore` xóa nhầm toàn bộ thư mục `.mvn/`. Thư mục Maven tải về/cache (thường dưới `~/.m2/wrapper/dists`) và kết quả `target/` là sản phẩm máy cục bộ, không phải các tệp cần commit để cố định công cụ.

## 4. Xác minh Maven đang chạy đúng bản đã chọn

Ở thư mục gốc dự án, sau khi đã có Wrapper:

~~~bash
./mvnw --version
./mvnw -B -ntp validate
~~~

Trên Windows PowerShell hoặc CMD:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp validate
~~~

Trong kết quả của `--version` phải có dòng thông báo phiên bản **Apache Maven 3.9.9**. Đường dẫn Maven home, tên hệ điều hành, Java runtime và thông tin môi trường sẽ khác nhau theo từng máy; không so sánh nguyên văn toàn bộ output. Lệnh `validate` kiểm tra việc Maven đọc và xử lý bước validate trong dự án có `pom.xml` hợp lệ; nó **không tương đương** chạy tất cả kiểm thử.

So sánh hai lệnh:

~~~bash
mvn --version
./mvnw --version
~~~

- `mvn` tra phiên bản Maven cài sẵn trên môi trường và `PATH`.
- `./mvnw` đi qua script Wrapper của repository và chọn Maven theo `distributionUrl`.
- Hai lệnh **có thể hiển thị các phiên bản khác nhau**; đó chính là lý do cần dùng Wrapper nhất quán.

Khi bản phân phối được tải lần đầu, Wrapper thường lưu nó trong cache Maven của người dùng; các lần chạy tiếp theo có thể sử dụng bản đã tải. Nếu chưa có bản phân phối trong cache, máy cần truy cập được URL cấu hình. Sau bước bootstrap, lệnh build vẫn dùng Maven và các repository dependency/plugin bình thường, vì vậy cố định Maven **không có nghĩa** mọi dependency đã sẵn sàng để build offline.

## 5. Cơ chế đọc distributionUrl và giới hạn của việc “pin”

Tương quan giữa các thành phần:

~~~text
Git checkout chứa: mvnw, mvnw.cmd, .mvn/wrapper/maven-wrapper.properties
          |
          v
     Chạy ./mvnw
          |
          v
 Wrapper đọc distributionUrl cố định
          |
          v
 Có Maven distro phù hợp trong cache?
       /                  \
     Có                    Chưa
      |                     |
      |               Tải archive từ URL
      |                     |
      |                Giải nén/cache
       \                  /
        v                v
          Chạy Maven 3.9.9
                 |
                 v
         Maven đọc pom.xml
                 |
                 v
    Lifecycle, plugin, dependency, build
~~~

**Phân phối đúng phiên bản** là điều kiện giúp lặp lại môi trường build, nhưng chưa đủ để build tái lập hoàn toàn. Kết quả vẫn có thể chịu ảnh hưởng bởi JDK, hệ điều hành, plugin, dependencies, profiles, repositories, biến môi trường, timestamps và dịch vụ bên ngoài.

Các điểm cần nắm:

- Thẻ `<version>` trong `pom.xml` nói về **phiên bản artifact của dự án**, không bảo Wrapper dùng phiên bản Maven đó.
- Thuộc tính `maven.compiler.release` nói về **mức ngôn ngữ/API và bytecode Java mục tiêu** của compiler plugin; không cài JDK và không chọn bản phân phối Maven.
- Maven Enforcer Plugin có thể kiểm tra phiên bản Maven/JDK và làm build fail khi không khớp, nhưng không tự tải Maven thay cho Wrapper. Dùng Wrapper để chọn Maven; dùng Enforcer khi cần thêm quy tắc xác nhận môi trường.
- `distributionUrl` pin **địa chỉ tệp**, nhưng nếu nội dung tại địa chỉ bị thay đổi trái phép thì chỉ pin URL chưa xác thực được toàn vẹn byte. Mục 7 mô tả cơ chế checksum.
- `wrapperUrl` (nếu xuất hiện) thường chỉ nguồn tải **maven-wrapper.jar** đối với những kiểu Wrapper cần JAR. Nó **khác** `distributionUrl`. Với `only-script`, không cần Wrapper JAR để chạy.
- `wrapperVersion` khác `distributionUrl`: thay một mình `wrapperVersion` không nâng cấp Apache Maven đang dùng; nâng cấp Wrapper cần cập nhật đúng bộ script/bootstrap tương ứng.

## 6. Nâng cấp hoặc hạ phiên bản Maven có kiểm soát

Ví dụ nhóm quyết định chuyển từ Maven 3.9.9 sang Maven 3.9.11. Một cách là sửa **duy nhất đường dẫn phân phối** trong `.mvn/wrapper/maven-wrapper.properties` để trỏ tới archive 3.9.11:

~~~properties
wrapperVersion=3.3.4
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
~~~

Đây là **ví dụ thay đổi phiên bản**, không phải một chỉ dẫn tự động cập nhật lên “bản mới nhất”. Chọn phiên bản Maven dựa trên tương thích plugin/JDK và chính sách của dự án. Các bước nâng/hạ cấp đáng tin cậy:

1. Chọn một bản phát hành Maven chính xác, kiểm tra archive tải được từ nguồn được phép.
2. Sửa `distributionUrl` sao cho số phiên bản trong đường dẫn **và** tên archive trùng nhau.
3. Nếu đã cấu hình `distributionSha256Sum`, **thay checksum bằng checksum của archive mới sau khi xác thực nguồn**; không giữ lại checksum của phiên bản cũ.
4. Chạy `./mvnw --version` rồi các lệnh build/test thực tế, ví dụ `./mvnw -B -ntp clean verify`.
5. Kiểm tra `git diff`, commit tệp properties (và các tệp Wrapper khác nếu được cập nhật), cho CI chạy cùng lệnh.
6. Nếu cần rollback, revert commit thay đổi hoặc sửa lại URL/checksum về bản phát hành trước đã được thử nghiệm.

Có thể yêu cầu plugin tạo lại Wrapper với phiên bản Maven mới:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=only-script
~~~

Cách này có thể thay cả các script/metadata Wrapper. Nếu mục tiêu chỉ đổi bản phân phối Maven và script hiện tại tương thích, sửa `distributionUrl` trực tiếp là thao tác nhỏ, dễ review hơn. Đừng chạy lệnh tạo Wrapper mà bỏ `-Dmaven` rồi mặc định kết luận nó giữ nguyên phiên bản đang pin: plugin có thể lấy phiên bản Maven runtime dùng để gọi nó.

## 7. Kiểm tra tính toàn vẹn: distributionSha256Sum

Cố định một URL HTTPS có phiên bản cụ thể hạn chế sai lệch nhưng chưa tự chứng minh nội dung archive đúng. Maven Wrapper hỗ trợ thuộc tính **`distributionSha256Sum`**: giá trị là **SHA-256 của file archive Maven được tải**, biểu diễn bằng 64 ký tự hexadecimal chữ thường. Khi cơ chế xác minh được triển khai và cấu hình đúng, Wrapper sẽ đối chiếu checksum để phát hiện nội dung tải xuống không khớp.

Quy trình thiết lập an toàn:

1. Xác định đúng tệp được `distributionUrl` trỏ tới, chẳng hạn `apache-maven-3.9.9-bin.zip`.
2. Lấy tệp từ nguồn phát hành đáng tin, **xác minh chữ ký PGP hoặc checksum SHA-512 chính thức theo hướng dẫn Apache**, trước khi dùng bản tải đó làm nguồn tính SHA-256.
3. Tính SHA-256 **trên chính file ZIP đã xác minh**:
   
   ~~~bash
   sha256sum apache-maven-3.9.9-bin.zip
   ~~~
   
   Hoặc trên PowerShell:
   
   ~~~powershell
   Get-FileHash -Algorithm SHA256 .\apache-maven-3.9.9-bin.zip
   ~~~

4. Thêm vào `maven-wrapper.properties` một dòng có khóa `distributionSha256Sum` và **giá trị băm thực tế đã đối chiếu**, không thêm khoảng trắng/ký tự khác. Commit cùng `distributionUrl`.
5. Thử bootstrap trên môi trường sạch có công cụ giải nén tương thích và xác nhận checksum được thực thi như kỳ vọng.

**Không thay SHA-256 bằng SHA-512**: trang phát hành Apache thường công bố file `.sha512`, nhưng thuộc tính `distributionSha256Sum` đòi hỏi **SHA-256**. Không chép một chuỗi băm không xác thực hoặc dùng lại checksum giữa các phiên bản, loại archive (`.zip` so với `.tar.gz`) hay nguồn phân phối có nội dung khác nhau.

Với kiểu `only-script`, cần quan tâm một tình huống thực tế: trên một số hệ Unix không có `unzip`, script có thể chuyển sang tải bản `.tar.gz`. Checksum SHA-256 của ZIP **không thể áp dụng cho TAR.GZ**, dẫn đến lỗi xác minh. Khi áp dụng checksum trên CI/container, hãy bảo đảm công cụ giải nén ZIP cần thiết có sẵn và thử thực tế trên runner mục tiêu; cân nhắc kiểu Wrapper khác theo yêu cầu triển khai nếu hệ thống không đáp ứng. Việc thiếu `unzip` khác với việc URL Maven bị ghi sai.

Một thuộc tính liên quan là `wrapperSha256Sum`, dành cho kiểm tra **maven-wrapper.jar** khi dùng kiểu Wrapper có JAR bootstrap. Nó không thay `distributionSha256Sum`. Với `only-script` không có Wrapper JAR, đừng nhầm hai đối tượng xác minh.

## 8. Áp dụng trên CI và trong nhóm

Sau khi các tệp Wrapper đã được commit, hệ thống CI nên chạy **Wrapper của repository**, tránh vô tình dùng Maven được cài sẵn trên runner.

Ví dụ GitHub Actions tối thiểu cho dự án cần JDK 17:

~~~yaml
name: Verify with pinned Maven

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Check Maven distribution
        run: ./mvnw --version
      - name: Build
        run: ./mvnw -B -ntp clean verify
~~~

Workflow này cài/chọn **JDK 17**, rồi sử dụng bản **Maven 3.9.9** theo file properties đã commit. Khi cập nhật `distributionUrl` qua pull request, CI sẽ thử bản mới trên cùng mã nguồn. Nếu thiết lập kiểm tra checksum, đảm bảo runner có hỗ trợ tải và giải nén phù hợp với loại archive.

Ý nghĩa các tham số: `-B` bật batch mode và `-ntp` tắt hiển thị tiến độ tải xuống trong log; `clean verify` yêu cầu làm sạch rồi chạy default lifecycle đến phase `verify`. Các bước integration test, scan, deploy hay publish chỉ xuất hiện nếu pipeline hoặc plugin đã cấu hình cho chúng.

Để giảm khác biệt giữa máy lập trình và CI, nên thống nhất quy ước:

| Hoạt động | Lệnh nên ưu tiên |
| --- | --- |
| Kiểm tra phiên bản Maven của dự án | `./mvnw --version` (Windows: `.\mvnw.cmd --version`) |
| Build/test tại máy cá nhân | `./mvnw -B -ntp verify` |
| Build trong CI | `./mvnw -B -ntp clean verify` |
| Kiểm tra chính xác những thay đổi cấu hình | `git diff -- .mvn/wrapper/maven-wrapper.properties` |
| Nâng phiên bản Maven có review | Sửa `distributionUrl`, cập nhật checksum nếu có, chạy test, commit |

Không bỏ qua kiểm tra JDK: Wrapper Maven pin Maven CLI nhưng **không đồng nhất `JAVA_HOME` trên mọi máy**. Với dự án đa module hoặc cần Java khác nhau để build, dùng Toolchains, cấu hình compiler plugin và/hoặc quy tắc Enforcer thích hợp.

## 9. Lỗi thường gặp và cách chẩn đoán

### 9.1. Chạy mvn thấy phiên bản khác với distributionUrl

Nguyên nhân: `mvn` gọi Maven toàn cục chứ không đi qua Wrapper. Kiểm tra bằng `./mvnw --version` hoặc `.\mvnw.cmd --version`. Cập nhật lệnh trong tài liệu và pipeline để tất cả dùng Wrapper.

### 9.2. Đã đổi distributionUrl nhưng Maven vẫn không chạy bản mong muốn

Kiểm tra đúng tên tệp `.mvn/wrapper/maven-wrapper.properties`, đúng script trong repository và kết quả `--version`. Xem số phiên bản trong **cả đường dẫn lẫn tên ZIP** có khớp không. Nếu plugin tạo lại script trong lúc nâng cấp, review và commit các thay đổi liên quan. Đừng sửa bừa cache trước khi kiểm tra URL và script.

### 9.3. Lần đầu chạy thất bại vì mạng, proxy, 401/403/404

Wrapper phải tải archive từ `distributionUrl` nếu máy chưa có trong cache. Kiểm tra DNS, proxy, TLS, quyền với repository nội bộ và tệp tại URL có thực sự tồn tại. `settings.xml` quản lý nhiều vấn đề resolution Maven dependency/plugin, nhưng không phải mọi cấu hình mirror ở đó đều tự động thay đổi một `distributionUrl` đã cố định. Trong mạng riêng, nhóm có thể quyết định dùng URL phân phối trong kho nội bộ được quản lý.

### 9.4. Java chưa cài hoặc phiên bản JDK không tương thích

Maven Wrapper **không thay JDK**. Kiểm tra `java -version`, `JAVA_HOME` và Java hiển thị bởi `./mvnw --version`. Chọn JDK tương thích với Maven, plugin và source code; cấu hình IDE/runner tương ứng. Lỗi compiler `invalid target release` thường liên quan JDK/toolchains hơn là việc URL Maven pin sai.

### 9.5. distributionSha256Sum không khớp

So đúng tệp ZIP/TAR.GZ, URL và checksum. Trên Linux với `only-script`, kiểm tra `unzip` có sẵn hay không vì một số bản script có thể chuyển sang archive khác. Không tắt xác minh một cách tùy tiện để bỏ qua lỗi; xác định nguyên nhân trước.

### 9.6. Có properties nhưng thiếu mvnw hoặc script không chạy được

Tệp properties không tự chạy Maven; repository cần các script tương ứng với loại Wrapper. Hãy sinh Wrapper bằng plugin ở project root, commit các tệp cần thiết, và với Linux/macOS giữ quyền thực thi cho `mvnw`.

### 9.7. Pin Maven xong nhưng build giữa hai máy vẫn khác nhau

Cần kiểm tra thêm phiên bản JDK, plugin và dependencies đã khai báo, snapshot dependency, profiles, settings, cấu hình repository, biến môi trường và dịch vụ ngoài. Pin Maven là **một phần của kiểm soát toolchain**, không phải cam kết mọi build luôn tạo ra artifact giống từng byte.

## 10. Checklist thực hành và tự kiểm tra

Trước khi kết thúc một thay đổi liên quan Maven Wrapper, xác nhận:

- [ ] `.mvn/wrapper/maven-wrapper.properties` nằm ở project root và được commit.
- [ ] `distributionUrl` dùng HTTPS và chỉ rõ **một phiên bản Maven** cùng tên archive tương ứng.
- [ ] `mvnw`/`mvnw.cmd` tồn tại, được commit và phù hợp với `distributionType`.
- [ ] `./mvnw --version` báo phiên bản Maven dự kiến trên ít nhất một môi trường sạch.
- [ ] CI chạy Wrapper thay vì Maven hệ thống và có JDK tương thích.
- [ ] Nếu pin checksum, `distributionSha256Sum` khớp archive **đã xác minh** và bootstrap đã được thử trên runner thực tế.
- [ ] Mọi nâng cấp/hạ cấp Maven đều được đưa qua review và test.

Ba câu hỏi để tự kiểm tra:

1. **Đổi `<version>` trong `pom.xml` từ 1.0.0 sang 2.0.0 có đổi Maven 3.9.9 thành 3.9.11 không?** Không. Đó là phiên bản artifact của dự án; Maven mà Wrapper chạy do `distributionUrl` quyết định.
2. **Máy đã cài Maven 3.9.11 nhưng `distributionUrl` pin 3.9.9, vậy `./mvnw --version` nên báo gì?** Maven **3.9.9**, miễn là Wrapper tải/khởi động được bản phân phối đã pin; `mvn --version` có thể báo 3.9.11.
3. **Tại sao đổi Maven từ 3.9.9 sang 3.9.11 thì phải cập nhật checksum?** Vì archive mới có bytes và SHA-256 khác; giữ băm cũ sẽ làm xác minh thất bại.

Tài liệu tham khảo chính thức:

- [Apache Maven Wrapper — cách hoạt động, phiên bản Maven và checksum](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — sử dụng và các loại phân phối](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Maven Wrapper Plugin: wrapper goal và các tham số](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)

**Ghi nhớ:** `distributionUrl` là khóa dùng để cố định **bản phân phối Maven**; `mvnw` và `mvnw.cmd` là cách bắt buộc người dùng và CI chạy bản đó. Commit cấu hình, xác minh phiên bản, chọn JDK phù hợp và kiểm tra toàn vẹn archive khi cần sẽ giúp quy trình build nhất quán và dễ kiểm toán.
