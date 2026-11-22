# Những tệp cần quản lý bằng Git và những đầu ra cần bỏ qua

Một dự án Java thường chứa nhiều loại tệp: mã nguồn, cấu hình build, thư viện, tài liệu, tệp kiểm thử, tệp do IDE tạo ra và các kết quả sinh ra trong quá trình biên dịch. Khi đưa dự án vào Git, ta cần quyết định tệp nào là một phần của dự án mà mọi thành viên cần nhận được, và tệp nào chỉ là kết quả tạm thời có thể tạo lại.

Nguyên tắc chung là quản lý những tệp thể hiện nội dung, cấu hình và quy trình cần thiết để xây dựng, kiểm thử, chạy và bảo trì dự án. Những đầu ra có thể tái tạo từ các tệp đó thường nên được bỏ qua. Quyết định đúng giúp repository gọn, tránh xung đột không cần thiết và giúp một người khác clone dự án rồi build lại được.

## 1. Git lưu lại điều gì trong một dự án?

Git theo dõi nội dung tệp được đưa vào vùng staging và commit. Git không tự hiểu một tệp là mã nguồn hay tệp sinh ra; người phát triển quyết định nội dung nào được quản lý.

Ví dụ, với một ứng dụng Java:

- Mã nguồn trong **src/main/java** mô tả hành vi của chương trình.
- Mã kiểm thử trong **src/test/java** mô tả cách xác nhận hành vi đó.
- **pom.xml** hoặc **build.gradle** mô tả cách biên dịch và các thư viện cần dùng.
- **.gitignore** mô tả những đường dẫn Git nên bỏ qua khi phát hiện tệp chưa được theo dõi.
- Thư mục **target** hoặc **build** thường chứa kết quả biên dịch, báo cáo và tệp trung gian có thể tạo lại.

Nếu một thành viên khác clone repository, những tệp được commit sẽ được lấy về. Những đầu ra bị bỏ qua sẽ được công cụ build tạo lại khi cần. Vì vậy, trước khi bỏ qua một tệp, hãy tự hỏi: nếu một thành viên mới không có tệp này, họ có thể tạo lại nó từ mã nguồn và cấu hình đã commit hay không?

## 2. Những tệp thường cần được quản lý bằng Git

### Mã nguồn và tài nguyên của ứng dụng

Đây là phần cốt lõi của dự án, thường gồm:

- Mã nguồn Java trong **src/main/java**.
- Tài nguyên ứng dụng trong **src/main/resources**, chẳng hạn tệp cấu hình mẫu, mẫu giao diện, thông điệp hoặc dữ liệu tĩnh cần thiết.
- Mã kiểm thử trong **src/test/java**.
- Tài nguyên kiểm thử trong **src/test/resources**.
- Các tệp SQL migration, script khởi tạo hoặc dữ liệu mẫu nhỏ cần thiết để tái hiện hành vi của ứng dụng.

Các tệp này là đầu vào của quá trình build hoặc là một phần của hành vi ứng dụng. Chúng cần được chia sẻ qua repository để mọi người cùng làm việc trên một phiên bản thống nhất.

### Tệp cấu hình công cụ build

Hãy commit các tệp mô tả cách dự án được xây dựng:

| Công cụ | Tệp thường được quản lý |
| --- | --- |
| Maven | **pom.xml** |
| Gradle | **build.gradle** hoặc **build.gradle.kts**, **settings.gradle** hoặc **settings.gradle.kts** |
| Gradle Version Catalog | **gradle/libs.versions.toml** nếu dự án sử dụng |
| Cấu hình build dùng chung | Các tệp cấu hình, script và task do nhóm duy trì |

Những tệp này cho biết phiên bản plugin, thư viện, cấu hình biên dịch, cấu hình kiểm thử và các bước build. Nếu không commit chúng, người khác có thể không biết cách tái tạo môi trường build của dự án.

Nếu dự án sử dụng dependency lockfile để cố định phiên bản thư viện đã phân giải, hãy commit lockfile theo chính sách của dự án. Điều này đặc biệt hữu ích với ứng dụng cần build có thể tái lập. Với thư viện dùng cho nhiều môi trường, nhóm cần thống nhất chính sách lockfile phù hợp với cách phát hành.

### Build wrapper

Wrapper cho phép thành viên chạy công cụ build bằng phiên bản mà dự án đã cấu hình, ngay cả khi họ chưa cài sẵn phiên bản đó trên máy.

Với Gradle, thông thường nên quản lý các tệp wrapper:

    gradlew
    gradlew.bat
    gradle/wrapper/gradle-wrapper.properties
    gradle/wrapper/gradle-wrapper.jar

Hai script **gradlew** và **gradlew.bat** là điểm khởi chạy trên các hệ điều hành tương ứng. Tệp properties xác định phiên bản Gradle cần dùng. Wrapper JAR là thành phần cần thiết trong cấu hình wrapper tiêu chuẩn, vì vậy không nên vô tình bỏ qua nó bằng một quy tắc ignore chung cho mọi tệp JAR.

Với Maven Wrapper, commit các script và cấu hình wrapper do dự án tạo ra, thường gồm:

    mvnw
    mvnw.cmd
    .mvn/wrapper/maven-wrapper.properties

Tùy loại wrapper và phiên bản Maven Wrapper, dự án có thể có thêm wrapper JAR hoặc tệp hỗ trợ khác trong **.mvn/wrapper**. Hãy quản lý các thành phần mà wrapper của repository thực sự cần để thành viên khác chạy được lệnh build.

### Tài liệu, script và cấu hình dùng chung

Các tệp sau thường nên được commit khi chúng phục vụ việc phát triển dự án:

- **README.md** hướng dẫn mục đích, cách cài đặt, build, chạy và kiểm thử.
- Tài liệu kiến trúc, quy ước code, hướng dẫn đóng góp và quyết định kỹ thuật.
- Script build, script chạy ứng dụng, script kiểm thử hoặc script chuẩn bị dữ liệu do nhóm duy trì.
- Tệp cấu hình CI, ví dụ workflow trong **.github/workflows**.
- Tệp cấu hình định dạng và kiểm tra mã nguồn dùng chung.
- Tệp cấu hình mẫu đã loại bỏ thông tin bí mật, ví dụ **.env.example**.

Một quy tắc hữu ích là commit cấu hình giúp mọi người có cùng quy trình, nhưng không commit giá trị riêng của tài khoản, máy cá nhân hoặc môi trường triển khai.

## 3. Những đầu ra thường nên bỏ qua

Đầu ra build thường có thể được tái tạo từ mã nguồn và cấu hình, vì vậy không cần đưa vào lịch sử Git.

| Loại tệp hoặc thư mục | Ví dụ | Lý do thường bỏ qua |
| --- | --- | --- |
| Bytecode Java | **.class** | Có thể biên dịch lại từ tệp **.java**. |
| Đầu ra Maven | **target/** | Chứa class, JAR, báo cáo và tệp trung gian do Maven tạo. |
| Đầu ra Gradle | **build/** | Chứa class, JAR, báo cáo và kết quả của các task. |
| Cache Gradle | **.gradle/** | Dữ liệu cache và trạng thái cục bộ của Gradle. |
| Thư mục biên dịch thủ công | **out/**, **bin/** | Chứa bytecode hoặc tệp sinh ra trong quá trình phát triển. |
| Gói phân phối được tạo tự động | Các tệp trong **dist/** nếu được build sinh ra | Có thể tái tạo từ mã nguồn và cấu hình. |
| Báo cáo kiểm thử | Báo cáo HTML, XML và thư mục test-results | Là kết quả của lần chạy kiểm thử. |
| Log và tệp tạm | **.log**, thư mục **tmp/** | Thường thay đổi liên tục và không phải đầu vào của dự án. |
| Cache công cụ | Cache IDE, cache build, cache phân tích mã | Được tạo lại theo máy hoặc theo lần chạy. |

Không nên chỉ nhìn phần mở rộng của một tệp để quyết định bỏ qua. Một tệp JAR trong **target/** có thể là đầu ra build và không cần commit, nhưng một JAR wrapper hoặc thư viện được dự án chủ động lưu trong **lib/** có thể là thành phần cần thiết. Hãy xét vai trò và vị trí của tệp.

### Cấu trúc dự án Java điển hình

Ví dụ một dự án Maven:

    product-app/
      .gitignore
      README.md
      pom.xml
      mvnw
      mvnw.cmd
      .mvn/
        wrapper/
          maven-wrapper.properties
      src/
        main/
          java/
            com/example/
              Main.java
          resources/
            application.properties
        test/
          java/
            com/example/
              MainTest.java
          resources/
      target/
        classes/
        test-classes/
        surefire-reports/

Trong ví dụ này, các tệp README, pom, wrapper, mã nguồn, tài nguyên và kiểm thử thường được commit. **target/** là đầu ra của Maven nên thường bị bỏ qua. Thành viên khác có thể tạo lại thư mục này bằng cách chạy build.

Ví dụ một dự án Gradle:

    product-app/
      .gitignore
      README.md
      settings.gradle
      build.gradle
      gradlew
      gradlew.bat
      gradle/
        wrapper/
          gradle-wrapper.properties
          gradle-wrapper.jar
      src/
        main/java/
        main/resources/
        test/java/
        test/resources/
      build/
      .gradle/

Các tệp build và wrapper được chia sẻ qua Git. **build/** và **.gradle/** thường được tạo lại và bỏ qua.

## 4. Dùng .gitignore để bỏ qua đầu ra

Tệp **.gitignore** chứa các mẫu đường dẫn mà Git cần bỏ qua khi xử lý những tệp chưa được theo dõi. Đặt một tệp **.gitignore** ở gốc repository giúp cả nhóm dùng chung quy tắc.

Ví dụ cho dự án Java dùng Maven hoặc Gradle:

    # Java bytecode
    *.class

    # Build outputs
    target/
    build/
    out/
    bin/
    dist/

    # Gradle cache
    .gradle/

    # Test and coverage reports
    coverage/
    test-results/

    # Logs and temporary files
    *.log
    tmp/
    temp/

    # Local environment files
    .env
    .env.*
    !.env.example
    application-local.properties

    # Operating system files
    .DS_Store
    Thumbs.db

Những mẫu này là điểm khởi đầu. Dự án có thể cần bổ sung hoặc điều chỉnh tùy công cụ, cấu trúc thư mục và quy ước của nhóm. Không nên thêm quy tắc ignore chỉ vì một tệp trông lạ; trước tiên hãy xác định tệp đó được tạo ra bởi công cụ nào và có cần thiết cho người khác hay không.

## 5. Cách đọc và viết mẫu trong .gitignore

Một số cú pháp thường gặp:

| Mẫu | Ý nghĩa |
| --- | --- |
| Mẫu tệp có đuôi .class | Bỏ qua các tệp có phần mở rộng **.class** ở mọi cấp thư mục. |
| **target/** | Bỏ qua các thư mục tên **target** ở mọi cấp thư mục. |
| **/target/** | Chỉ bỏ qua thư mục **target** ngay tại gốc repository. |
| **logs/*.log** | Bỏ qua các tệp log nằm trực tiếp trong thư mục **logs**. |
| Thư mục tên generated ở mọi cấp | Bỏ qua thư mục **generated** ở bất kỳ cấp nào. |
| **!important.log** | Ngoại lệ: đưa mẫu tệp này ra khỏi nhóm bị bỏ qua nếu các điều kiện thư mục cha cho phép. |
| **# comment** | Dòng chú thích, không phải mẫu đường dẫn. |

Một mẫu không chứa dấu gạch chéo thường có thể khớp tên ở nhiều cấp thư mục. Dấu gạch chéo ở đầu mẫu neo đường dẫn vào gốc của tệp **.gitignore**. Dấu gạch chéo ở cuối cho biết mẫu áp dụng cho thư mục.

Ký tự **!** dùng để loại một đường dẫn khỏi các quy tắc ignore trước đó. Ví dụ:

    .env.*
    !.env.example

Quy tắc đầu tiên bỏ qua các tệp có tên bắt đầu bằng **.env.**; quy tắc thứ hai cho phép theo dõi lại **.env.example**. Tệp mẫu phải chứa giá trị giả hoặc hướng dẫn, tuyệt đối không chứa mật khẩu, token hay khóa thật.

Ngoại lệ chỉ hoạt động nếu Git có thể đi vào các thư mục cha. Nếu một thư mục cha đã bị bỏ qua hoàn toàn, chỉ thêm quy tắc ngoại lệ cho tệp con có thể chưa đủ; cần điều chỉnh cả quy tắc cho thư mục cha.

Có thể đặt **.gitignore** ở thư mục con để áp dụng quy tắc cho khu vực đó. Mẫu trong mỗi tệp được xét tương đối với vị trí của tệp **.gitignore** tương ứng. Với dự án thông thường, một tệp ở gốc repository là nơi thuận tiện để quản lý các quy tắc chung.

## 6. Phân biệt tệp dùng chung và cấu hình riêng của máy

Một số tệp cấu hình có thể hữu ích cho cả nhóm, trong khi những tệp khác chứa đường dẫn, tùy chọn hoặc thông tin chỉ đúng trên máy của một người.

### Tệp IDE

Các IDE có thể tạo thư mục hoặc tệp cấu hình riêng:

- IntelliJ IDEA có thư mục **.idea/** và các tệp module **.iml**.
- Eclipse có các tệp như **.project**, **.classpath** và thư mục **.settings/**.
- Visual Studio Code có thư mục **.vscode/**.

Không có một quy tắc duy nhất phù hợp cho mọi nhóm. Một số thiết lập IDE như formatter, quy tắc kiểm tra mã hoặc cấu hình chạy dùng chung có thể nên được commit. Ngược lại, workspace, đường dẫn tuyệt đối, danh sách plugin cá nhân và trạng thái cửa sổ thường chỉ thuộc về máy của từng người.

Vì vậy, có thể bỏ qua toàn bộ một thư mục IDE nếu nhóm không dùng cấu hình trong đó. Nếu nhóm cần chia sẻ một vài tệp, hãy ignore các tệp cá nhân và cho phép theo dõi những tệp dùng chung bằng các mẫu ngoại lệ phù hợp. Tránh vô tình loại bỏ cấu hình định dạng hoặc quy tắc code mà dự án yêu cầu.

### Cấu hình môi trường và bí mật

Không commit tệp chứa mật khẩu cơ sở dữ liệu, API key, access token, private key hoặc thông tin đăng nhập. Ví dụ, **.env**, **application-local.properties** và cấu hình Maven/Gradle cá nhân có thể chứa dữ liệu riêng.

Thay vào đó:

1. Commit một tệp mẫu như **.env.example** với tên biến và giá trị minh họa không nhạy cảm.
2. Hướng dẫn thành viên tự tạo tệp cấu hình cục bộ từ mẫu.
3. Đưa thông tin bí mật vào biến môi trường hoặc kho quản lý secret phù hợp với môi trường triển khai.
4. Kiểm tra nội dung trước khi staging và commit.

Không phải mọi tệp có tên **application.properties** hay **gradle.properties** đều cần ignore. Nếu chúng chứa cấu hình mặc định dùng chung, có thể commit. Chỉ tách hoặc bỏ qua phần chứa thông tin riêng và bí mật.

## 7. .gitignore không tự bỏ theo dõi tệp đã được commit

Đây là điểm rất quan trọng: **.gitignore chủ yếu ngăn Git đề xuất thêm các tệp chưa được theo dõi**. Nếu một tệp đã được Git theo dõi, thêm đường dẫn của nó vào **.gitignore** không làm Git ngừng theo dõi tệp đó.

Ví dụ, repository đã commit một số tệp trong **target/**. Sau đó nhóm thêm:

    target/

Git vẫn tiếp tục phát hiện thay đổi ở những tệp target đã được theo dõi. Muốn giữ tệp trên máy nhưng bỏ nó khỏi chỉ mục Git, dùng:

    git rm --cached -r target

Sau đó kiểm tra:

    git status

Lệnh **git rm --cached** loại tệp khỏi chỉ mục theo dõi của Git nhưng giữ bản làm việc trên máy. Khi commit thay đổi này, các tệp đó được bỏ khỏi repository ở những phiên bản tiếp theo; các thành viên khác sẽ nhận việc xóa khỏi repository khi cập nhật. Bản thân thư mục đầu ra vẫn có thể được build lại.

Chỉ thực hiện thao tác này sau khi xác nhận đường dẫn đúng là đầu ra cần bỏ theo dõi. Không dùng lệnh xóa hàng loạt trên thư mục mã nguồn hoặc dữ liệu có giá trị.

## 8. Kiểm tra quy tắc ignore bằng lệnh Git

### Xem trạng thái repository

    git status --short

Lệnh này hiển thị các tệp mới, tệp đã sửa và thay đổi trong staging. Các tệp bị ignore thường không xuất hiện trong trạng thái thông thường.

Muốn xem cả tệp bị ignore:

    git status --short --ignored

Ký hiệu hiển thị giúp nhận biết những đường dẫn Git đang bỏ qua.

### Tìm quy tắc khiến một tệp bị bỏ qua

    git check-ignore -v target/classes/com/example/Main.class

Tùy chọn **-v** hiển thị tệp **.gitignore** và dòng quy tắc đã khớp. Điều này hữu ích khi một tệp bị bỏ qua ngoài dự kiến hoặc một quy tắc quá rộng đang ảnh hưởng tới tệp cần commit.

### Kiểm tra tệp đã được theo dõi hay chưa

    git ls-files target

Nếu đường dẫn đã được theo dõi, kết quả có thể vẫn xuất hiện dù đã thêm quy tắc ignore. Khi đó, cần xử lý chỉ mục như phần trước nếu muốn ngừng theo dõi.

### Thêm tệp cần quản lý

Sau khi xác định các tệp nguồn và cấu hình cần commit, có thể staging chúng:

    git add .gitignore
    git add pom.xml README.md src
    git status

Với dự án Gradle, thay **pom.xml** bằng các tệp cấu hình Gradle và thêm wrapper tương ứng. Trước khi commit, đọc danh sách staging để chắc chắn không có log, đầu ra build, cấu hình cá nhân hoặc bí mật.

## 9. Những nơi lưu quy tắc ignore khác

Git có một số nơi để khai báo mẫu ignore:

- **.gitignore** trong repository: được commit và chia sẻ với mọi thành viên.
- **.git/info/exclude**: chỉ áp dụng trong repository hiện tại trên máy đang dùng, không được commit.
- Tệp ignore toàn cục: áp dụng cho nhiều repository trên máy cá nhân, thường dùng cho tệp hệ điều hành hoặc tệp tạm của editor.

Các quy tắc dùng chung cho dự án nên nằm trong **.gitignore**. **.git/info/exclude** và ignore toàn cục phù hợp với các tệp cá nhân mà nhóm không cần thống nhất. Không nên dùng ignore toàn cục để che giấu một tệp dự án mà cả nhóm cần quyết định cách quản lý.

## 10. Quy trình lựa chọn và commit tệp an toàn

Khi bắt đầu một repository Java mới hoặc đưa một dự án hiện có vào Git, có thể thực hiện theo trình tự:

1. Xác định mã nguồn, tài nguyên, kiểm thử, tài liệu và cấu hình build cần thiết.
2. Xác định công cụ build đang dùng và giữ lại wrapper cùng cấu hình phiên bản của nó.
3. Xác định các thư mục sinh ra như **target/**, **build/**, **out/**, **bin/**, cache và báo cáo.
4. Tạo hoặc cập nhật **.gitignore** ở gốc repository.
5. Tạo tệp cấu hình mẫu không chứa bí mật nếu ứng dụng cần cấu hình theo môi trường.
6. Chạy **git status --short --ignored** và **git check-ignore -v** khi cần để kiểm tra kết quả.
7. Stage các tệp dự án cần chia sẻ, xem lại **git status** và nội dung diff trước khi commit.
8. Thử clone repository vào một thư mục mới, làm theo README và chạy build bằng wrapper để xác nhận các tệp đã commit đủ cho người khác tái tạo đầu ra.

Việc thử build từ một bản clone sạch là cách kiểm tra thực tế rất hữu ích. Nếu build thất bại vì thiếu một tệp cấu hình dùng chung hoặc wrapper, hãy xác định tệp đó có phải đầu vào của dự án hay không rồi cập nhật repository. Nếu chỉ thiếu thông tin bí mật hoặc cấu hình cá nhân, hãy bổ sung hướng dẫn thiết lập cục bộ thay vì đưa bí mật vào Git.

## 11. Một số sai lầm cần tránh

### Commit cả thư mục đầu ra

Commit **target/** hoặc **build/** làm repository tăng kích thước và tạo ra nhiều thay đổi nhiễu mỗi lần build. Các tệp này thường được sinh lại nên nên bỏ qua.

### Ignore quá rộng

Quy tắc ignore tất cả tệp có phần mở rộng .jar có thể bỏ qua cả thư viện được dự án chủ động lưu hoặc JAR cần cho wrapper. Tương tự, ignore mọi tệp **.xml** có thể làm mất cấu hình Maven và tài nguyên XML. Hãy ưu tiên ignore theo thư mục đầu ra hoặc mẫu cụ thể.

### Nghĩ rằng thêm .gitignore sẽ xóa tệp khỏi Git

Tệp đã được theo dõi vẫn được Git theo dõi. Cần loại nó khỏi chỉ mục bằng thao tác phù hợp rồi commit thay đổi đó.

### Bỏ qua wrapper

Nếu chỉ commit cấu hình build nhưng quên wrapper, thành viên mới có thể phải tự cài đúng phiên bản công cụ. Giữ các tệp wrapper cần thiết giúp lệnh build nhất quán hơn.

### Đưa bí mật vào repository

Ignore tệp bí mật trước khi staging và kiểm tra nội dung diff. Nếu bí mật đã được commit hoặc đẩy lên remote, xóa tệp ở commit mới không làm bí mật biến mất khỏi lịch sử cũ; cần thu hồi hoặc xoay vòng thông tin đó và xử lý lịch sử theo quy trình của nhóm.

### Ignore cấu hình IDE mà cả nhóm cần

Một số thiết lập IDE là quy ước chung của dự án. Hãy thống nhất với nhóm tệp nào cần chia sẻ, sau đó viết quy tắc ignore đủ cụ thể để giữ lại chúng.

## 12. Kết luận về cách phân loại

Khi phân loại một tệp, hãy xem nó có phải nguồn dữ liệu hoặc cấu hình cần thiết để tạo ra sản phẩm hay không. Mã nguồn, kiểm thử, tài liệu, build script, wrapper và cấu hình dùng chung thường thuộc Git. Bytecode, thư mục build, cache, báo cáo, log, tệp tạm và trạng thái IDE cá nhân thường được bỏ qua.

Một repository tốt cho phép người khác lấy mã nguồn và cấu hình đã commit, hiểu cách thiết lập môi trường, rồi tạo lại các đầu ra bằng công cụ build của dự án. **.gitignore** hỗ trợ giữ repository tập trung vào những thành phần cần chia sẻ; việc xem lại staging và thử build từ bản clone sạch giúp xác nhận quyết định đó.
