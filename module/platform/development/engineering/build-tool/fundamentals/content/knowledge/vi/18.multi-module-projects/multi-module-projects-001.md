# Khi nào cần chia một dự án thành nhiều mô-đun build

Một dự án Java có thể bắt đầu với một mô-đun duy nhất: mã nguồn, tài nguyên, kiểm thử và cấu hình build cùng nằm trong một project. Khi dự án lớn dần, nhiều phần của hệ thống có thể có trách nhiệm, dependency, nhịp thay đổi và cách kiểm thử khác nhau. Khi đó, chia dự án thành nhiều mô-đun build có thể giúp kiểm soát phụ thuộc, tái sử dụng thành phần và tổ chức quy trình phát triển tốt hơn.

Tuy nhiên, nhiều mô-đun không tự động làm dự án tốt hơn. Mỗi mô-đun mới tạo thêm cấu hình, ranh giới dependency, quy tắc version, bước build và chi phí phối hợp. Nếu chỉ chia theo số lượng package hoặc theo cảm giác rằng dự án đã lớn, hệ thống có thể trở nên khó hiểu hơn mà không có lợi ích thực tế.

Quyết định nên dựa trên những vấn đề mà cấu trúc hiện tại đang gây ra: các phần có cần được build và kiểm thử độc lập không, có ranh giới trách nhiệm rõ ràng không, có thể tái sử dụng hoặc phát hành riêng không, và chi phí phối hợp giữa các phần có đáng kể không. Bài học này trình bày các dấu hiệu, lợi ích, đánh đổi và cách chuyển từ một mô-đun sang nhiều mô-đun với Maven hoặc Gradle.

## 1. Mô-đun build là gì?

Mô-đun build là một đơn vị được công cụ build nhận diện và quản lý riêng. Tùy công cụ, nó có thể có:

- Mã nguồn và tài nguyên riêng.
- Dependency trực tiếp và bắc cầu riêng.
- Cấu hình compiler, test và đóng gói riêng.
- Tập tác vụ build riêng.
- Artifact đầu ra riêng, chẳng hạn JAR.
- Các mô-đun khác phụ thuộc vào nó.

Ví dụ một ứng dụng có thể được chia thành:

    product-system/
      domain/
      application/
      web/
      infrastructure/

Mỗi thư mục có thể là một mô-đun build. Mô-đun domain chứa các quy tắc nghiệp vụ cốt lõi; application điều phối use case; web cung cấp HTTP API; infrastructure triển khai truy cập cơ sở dữ liệu hoặc dịch vụ ngoài.

Mô-đun build có ranh giới rõ ràng về mã nguồn và dependency. Nó không chỉ là một thư mục con hoặc package Java.

### Phân biệt package, mô-đun build và Java module

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Vai trò |
| --- | --- |
| Package Java | Nhóm lớp và kiểu theo namespace, ví dụ com.example.domain. |
| Mô-đun build | Đơn vị Maven/Gradle có cấu hình, dependency và đầu ra build riêng. |
| Java Platform Module System (JPMS) | Hệ thống module ở cấp ngôn ngữ/runtime, thường khai báo bằng module-info.java. |

Một mô-đun Maven hoặc Gradle không bắt buộc phải là một JPMS module. Có thể chia build thành nhiều mô-đun mà vẫn đóng gói các lớp theo package truyền thống trên classpath. Ngược lại, một mô-đun build có thể chứa nhiều package Java.

Việc chia mô-đun build là quyết định về cấu trúc phát triển và build. Việc dùng JPMS là quyết định bổ sung về module system, khả năng đọc (readability), exports và encapsulation ở runtime/compile time.

## 2. Khi một mô-đun duy nhất vẫn là lựa chọn tốt

Một mô-đun đơn giản thường là lựa chọn phù hợp khi:

- Dự án còn nhỏ hoặc có một nhóm chức năng liên kết chặt chẽ.
- Các phần luôn được thay đổi, build và phát hành cùng nhau.
- Dependency giữa các phần đơn giản và dễ hiểu.
- Thời gian build vẫn đáp ứng nhu cầu của nhóm.
- Một bộ kiểm thử chung đủ để xác nhận hành vi.
- Chưa có nhu cầu tái sử dụng một phần của dự án ở ứng dụng khác.

Ví dụ một ứng dụng nội bộ có vài màn hình, một lớp service, một lớp repository và một database có thể được tổ chức tốt bằng package:

    src/main/java/
      com/example/controller/
      com/example/service/
      com/example/repository/
      com/example/model/

Việc tách thành bốn mô-đun build chỉ để mỗi package có một thư mục riêng có thể làm tăng cấu hình mà không tạo ra ranh giới có ý nghĩa. Các phần vẫn cần thay đổi cùng nhau, phụ thuộc qua lại và được triển khai như một ứng dụng duy nhất.

Không cần đặt mục tiêu có nhiều mô-đun. Cấu trúc build nên phản ánh nhu cầu thực tế của dự án.

## 3. Những dấu hiệu cho thấy nên cân nhắc tách mô-đun

Không có một ngưỡng cố định về số dòng mã, số lớp hoặc thời gian build để quyết định. Nên xem xét nhiều dấu hiệu cùng lúc.

### Các phần có trách nhiệm khác nhau và ranh giới ổn định

Một phần có thể đại diện cho một năng lực nghiệp vụ hoặc một lớp kiến trúc có API tương đối rõ. Ví dụ:

- domain model và quy tắc nghiệp vụ;
- ứng dụng hoặc use case;
- adapter HTTP hoặc giao diện người dùng;
- adapter cơ sở dữ liệu;
- thư viện dùng chung cho nhiều ứng dụng.

Nếu các phần có thể được mô tả bằng một hợp đồng dependency rõ ràng, chúng có tiềm năng trở thành mô-đun.

### Nhiều thành phần cần dùng chung một thư viện nội bộ

Giả sử hai ứng dụng cùng sử dụng quy tắc tính giá. Nếu mã nguồn quy tắc nằm bên trong một ứng dụng, ứng dụng còn lại có thể phải sao chép mã hoặc phụ thuộc vào cấu trúc không phù hợp. Tách phần quy tắc thành một thư viện riêng cho phép cả hai phụ thuộc vào cùng một artifact.

Điều này chỉ có lợi khi thư viện có API ổn định và thật sự được tái sử dụng. Không nên tạo một mô-đun chỉ để chứa vài hàm tiện ích chưa có ranh giới rõ ràng.

### Build hoặc kiểm thử toàn bộ dự án quá tốn thời gian

Trong dự án lớn, một thay đổi nhỏ có thể kích hoạt biên dịch và kiểm thử rất nhiều phần không liên quan. Mô-đun có dependency được mô tả chính xác có thể giúp build chỉ thực hiện những tác vụ cần thiết.

Tách mô-đun không tự động bảo đảm build nhanh hơn. Nếu mọi mô-đun đều phụ thuộc lẫn nhau, một thay đổi nhỏ vẫn lan tới gần như toàn bộ đồ thị. Lợi ích xuất hiện khi ranh giới dependency cho phép cô lập công việc.

### Các phần có nhịp thay đổi hoặc người sở hữu khác nhau

Một nhóm có thể sở hữu thư viện domain, nhóm khác sở hữu adapter tích hợp. Nếu các phần có API rõ và ít thay đổi chéo, mô-đun riêng có thể giúp review, kiểm thử và kiểm soát thay đổi.

Sự khác biệt về người sở hữu chỉ là một tín hiệu. Nếu hai nhóm vẫn phải chỉnh sửa cùng một tập lớp trong mỗi thay đổi, việc tách build có thể không giải quyết được sự phụ thuộc tổ chức.

### Cần phát hành hoặc triển khai một phần riêng

Một thư viện có thể có vòng đời version và phát hành riêng với ứng dụng sử dụng nó. Mô-đun riêng giúp tạo artifact độc lập, khai báo dependency và xuất bản lên repository.

Nếu toàn bộ hệ thống luôn được triển khai cùng nhau, không cần phát hành độc lập và không có nhu cầu tái sử dụng, một build nhiều mô-đun nội bộ có thể đủ; không nhất thiết phải chia thành nhiều repository hoặc nhiều pipeline.

### Cần cô lập dependency hoặc môi trường

Một adapter có thể cần thư viện JDBC, client cloud hoặc SDK đặc thù. Mã domain không cần những thư viện đó. Tách mô-đun giúp giữ dependency ở đúng khu vực và giảm nguy cơ các thư viện hạ tầng lan vào classpath của phần nghiệp vụ.

Đây là lợi ích đáng kể khi muốn giữ API cốt lõi nhỏ, giảm coupling và làm cho các lớp dễ kiểm thử hơn.

## 4. Lợi ích thực tế của nhiều mô-đun

### Ranh giới dependency rõ hơn

Khi một mô-đun chỉ khai báo dependency cần thiết, build có thể thể hiện phần nào được phép sử dụng phần nào. Ví dụ:

    web
      |
      v
    application
      |
      v
    domain

    infrastructure
      |
      v
    application / domain API

Hướng phụ thuộc cần được thiết kế theo kiến trúc. Nếu domain không cần biết web framework hoặc database driver, domain không nên phụ thuộc vào mô-đun web hay infrastructure.

### Tái sử dụng artifact

Một mô-đun thư viện có thể được sử dụng từ nhiều ứng dụng trong cùng build hoặc được publish để dự án khác tiêu thụ. Các ứng dụng dùng cùng artifact thay vì sao chép mã nguồn.

### Kiểm thử và build theo phạm vi

Có thể chạy test của một mô-đun hoặc build một mô-đun cùng các dependency cần thiết. Điều này hữu ích khi phát triển một phần độc lập.

### Tách cấu hình và dependency

Mô-đun web có thể khai báo framework HTTP; mô-đun infrastructure khai báo driver database; mô-đun domain chỉ phụ thuộc vào những thư viện thực sự cần. Điều này giúp classpath gọn và làm rõ dependency nào thuộc trách nhiệm nào.

### Tổ chức phát hành

Một thư viện có thể có version, changelog và artifact riêng. Các ứng dụng có thể nâng cấp thư viện theo lịch phù hợp thay vì phải lấy toàn bộ repository.

## 5. Những chi phí và rủi ro khi tách mô-đun

Mỗi mô-đun mới tạo ra một ranh giới cần duy trì. Các chi phí thường gặp:

- Thêm cấu hình Maven POM hoặc Gradle build script.
- Quản lý version plugin, compiler và dependency dùng chung.
- Thiết kế API công khai giữa các mô-đun.
- Tổ chức kiểm thử tích hợp qua ranh giới mô-đun.
- Quản lý artifact, repository và quy trình publish nếu phát hành riêng.
- Điều tra lỗi dependency và thứ tự build phức tạp hơn.
- Phối hợp thay đổi khi API giữa các mô-đun thay đổi.
- Cấu hình IDE, CI và công cụ phân tích cho nhiều project.

Nếu mô-đun quá nhỏ, người phát triển phải chuyển qua lại nhiều build file, nhưng không đạt được khả năng cô lập thực sự. Nếu mô-đun quá lớn, ranh giới vẫn mờ và lợi ích tách biệt không rõ.

Một dấu hiệu của thiết kế chưa tốt là các mô-đun phụ thuộc vòng, phải truy cập lớp nội bộ của nhau hoặc thường xuyên sửa đồng thời nhiều mô-đun chỉ để hoàn thành một thay đổi nhỏ.

## 6. Chọn ranh giới mô-đun theo trách nhiệm và dependency

Ranh giới tốt thường xuất phát từ một trách nhiệm hoặc năng lực có thể mô tả rõ, thay vì một quy tắc chia đều số lượng lớp.

### Tách theo lớp kiến trúc

Ví dụ:

    shop/
      domain/
      application/
      infrastructure/
      web/

- domain chứa entity, value object và quy tắc nghiệp vụ.
- application chứa use case và điều phối nghiệp vụ.
- infrastructure triển khai lưu trữ, messaging và kết nối hệ thống ngoài.
- web chứa controller, request/response model và cấu hình HTTP.

Cấu trúc này có thể phù hợp khi các lớp kiến trúc có dependency và kiểm thử riêng. Tuy nhiên, nếu mỗi lớp chỉ có một vài lớp mỏng và luôn thay đổi cùng nhau, việc tách thành mô-đun riêng có thể chưa cần thiết.

### Tách theo năng lực nghiệp vụ

Với hệ thống lớn, có thể tách theo business capability:

    commerce/
      catalog/
      ordering/
      payment/
      shipping/

Mỗi năng lực có thể chứa các package hoặc mô-đun con theo nhu cầu. Cách này giúp ranh giới phản ánh ngôn ngữ và quy tắc nghiệp vụ.

Không nên tách quá sớm thành hàng chục mô-đun chỉ vì sơ đồ kiến trúc có nhiều ô. Hãy bắt đầu từ các ranh giới có API rõ và có nhu cầu build/reuse/test độc lập.

### Tách thư viện dùng chung

Một thư viện nội bộ có thể được tách khi:

- Có nhiều consumer thực sự.
- API ổn định và có thể được version hóa.
- Có thể kiểm thử độc lập.
- Không phụ thuộc vào ứng dụng cụ thể đang sử dụng nó.

Tránh tạo một mô-đun common hoặc utils chứa mọi thứ không biết đặt ở đâu. Mô-đun dùng chung quá rộng thường trở thành điểm phụ thuộc của toàn bộ hệ thống và khó thay đổi.

## 7. Thiết kế hướng phụ thuộc và tránh chu trình

Một build nhiều mô-đun nên tạo thành đồ thị dependency có hướng và không có chu trình. Nếu A phụ thuộc B, B không nên phụ thuộc ngược lại A.

Ví dụ hợp lý:

    web -----> application -----> domain
                  ^
                  |
    infrastructure

Ví dụ có chu trình:

    module-a -----> module-b
       ^               |
       |_______________|

Chu trình làm cho thứ tự build không thể xác định theo cách thông thường và thường cho thấy trách nhiệm hoặc API chưa được phân chia hợp lý.

Khi hai mô-đun cần dùng chung một kiểu dữ liệu, có thể:

- Đưa hợp đồng ổn định vào mô-đun API nhỏ hơn.
- Chuyển kiểu dữ liệu về mô-đun domain phù hợp.
- Đảo hướng dependency thông qua interface.
- Gộp hai mô-đun nếu chúng thực sự không thể thay đổi độc lập.

Không nên tạo mô-đun API chỉ để phá chu trình nếu nó chỉ chuyển tiếp mọi lớp nội bộ. Mô-đun đó cần thể hiện hợp đồng có ý nghĩa.

## 8. Khi nào cần mô-đun build độc lập và khi nào chỉ cần package?

Một số câu hỏi giúp phân biệt:

| Nhu cầu | Package có thể đủ? | Mô-đun build có lợi ích rõ? |
| --- | --- | --- |
| Chỉ muốn nhóm lớp theo chức năng | Có | Thường chưa cần |
| Muốn ẩn package và tổ chức namespace | Có | Có thể, nhưng không bắt buộc |
| Cần dependency riêng và classpath riêng | Không đủ | Có |
| Cần build/test một phần cùng dependency của nó | Không đủ | Có |
| Cần tạo JAR riêng để nhiều ứng dụng dùng | Không đủ | Có |
| Cần version và publish độc lập | Không đủ | Có |
| Các phần luôn thay đổi và phát hành cùng nhau | Thường đủ | Chỉ khi có lý do khác |

Package là công cụ tổ chức mã nguồn bên trong mô-đun. Mô-đun build tạo ranh giới cho cấu hình và dependency. Có thể dùng cả hai cùng lúc.

## 9. Cấu trúc nhiều mô-đun với Maven

Maven hỗ trợ multi-module build bằng một POM cha có packaging **pom** và phần **modules**.

Ví dụ:

    shop/
      pom.xml
      domain/
        pom.xml
        src/main/java/
      application/
        pom.xml
        src/main/java/
      web/
        pom.xml
        src/main/java/

POM gốc:

    <project>
        <modelVersion>4.0.0</modelVersion>
        <groupId>com.example.shop</groupId>
        <artifactId>shop-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <packaging>pom</packaging>

        <modules>
            <module>domain</module>
            <module>application</module>
            <module>web</module>
        </modules>
    </project>

Mỗi mô-đun con có POM riêng và có thể kế thừa parent:

    <parent>
        <groupId>com.example.shop</groupId>
        <artifactId>shop-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>application</artifactId>

Nếu application phụ thuộc domain:

    <dependencies>
        <dependency>
            <groupId>com.example.shop</groupId>
            <artifactId>domain</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>

Trong Maven reactor, các mô-đun được xây dựng theo thứ tự phụ thuộc. Khi gọi build ở root, Maven có thể xác định thứ tự phù hợp thay vì chỉ theo thứ tự thư mục.

Một số lệnh hữu ích:

    mvn clean verify
    mvn -pl application -am test
    mvn -pl web -am package

- **-pl** chọn một hoặc nhiều project.
- **-am** build thêm các project mà project được chọn phụ thuộc.
- **clean verify** chạy lifecycle phù hợp cho toàn bộ reactor.

Parent POM và aggregator POM có thể là cùng một tệp, nhưng hai vai trò này khác nhau: aggregator tập hợp mô-đun để build; parent cung cấp cấu hình được kế thừa. Một dự án có thể dùng cùng một POM cho cả hai hoặc tách vai trò khi cấu trúc phức tạp.

## 10. Cấu trúc nhiều mô-đun với Gradle

Gradle multi-project build xác định các project trong settings.gradle hoặc settings.gradle.kts.

Ví dụ cấu trúc:

    shop/
      settings.gradle
      build.gradle
      domain/
        build.gradle
        src/main/java/
      application/
        build.gradle
        src/main/java/
      web/
        build.gradle
        src/main/java/

Tệp settings.gradle:

    rootProject.name = 'shop'
    include 'domain', 'application', 'web'

Tệp build.gradle ở root có thể khai báo plugin hoặc cấu hình dùng chung:

    plugins {
        id 'base'
    }

    subprojects {
        repositories {
            mavenCentral()
        }
    }

Mô-đun application khai báo dependency tới domain:

    plugins {
        id 'java-library'
    }

    dependencies {
        implementation project(':domain')
    }

Mô-đun web có thể phụ thuộc application:

    plugins {
        id 'application'
    }

    dependencies {
        implementation project(':application')
    }

Gradle tạo project dependency và task graph tương ứng. Khi chạy:

    ./gradlew :application:test

Gradle có thể build các project dependency cần thiết trước khi thực hiện test của application.

Một số lệnh hữu ích:

    ./gradlew projects
    ./gradlew :domain:build
    ./gradlew :web:build
    ./gradlew build

Task path đầy đủ giúp xác định project cụ thể. Trên Windows có thể dùng gradlew.bat.

## 11. Dùng java-library hay application cho mô-đun?

Trong Gradle, plugin **java-library** phù hợp với mô-đun tạo thư viện Java. Plugin này cung cấp cấu hình API và implementation để thể hiện dependency được công khai cho consumer hay chỉ dùng nội bộ.

Plugin **application** phù hợp với mô-đun ứng dụng có entry point và có thể chạy bằng task run. Nó áp dụng các khả năng của Java plugin và bổ sung cấu hình ứng dụng.

Ví dụ:

    plugins {
        id 'java-library'
    }

    dependencies {
        api 'com.example:public-api:1.0'
        implementation 'com.example:internal-helper:2.0'
    }

Dependency **api** có thể được đưa vào compile classpath của consumer thông qua API công khai; **implementation** được giữ nội bộ hơn và không tự lan vào compile classpath của consumer theo cùng cách. Chọn đúng cấu hình giúp giảm dependency bị lộ và giảm recompilation không cần thiết ở consumer.

Với Maven, dependency scope và cấu trúc POM quyết định dependency được truyền tiếp như thế nào. Cần xác định thư viện nào là một phần của API công khai và thư viện nào chỉ là implementation detail.

## 12. Chia mô-đun để tăng tốc build: điều kiện cần

Nhiều mô-đun có thể hỗ trợ incremental build và chạy song song, nhưng không phải cứ chia nhỏ là build nhanh hơn.

Lợi ích có thể xuất hiện khi:

- Thay đổi trong một mô-đun không làm thay đổi API mà nhiều mô-đun khác dùng.
- Dependency graph chính xác, không có phụ thuộc không cần thiết.
- Mô-đun có đầu vào và đầu ra được khai báo tốt.
- Có thể chạy task độc lập song song.
- Các kiểm thử nặng được tách theo phạm vi phù hợp.
- Build cache có thể tái sử dụng kết quả của các mô-đun không đổi.

Ngược lại, nếu một mô-đun common bị thay đổi liên tục và mọi mô-đun đều phụ thuộc vào nó, mỗi thay đổi có thể làm phần lớn build chạy lại. Nếu các mô-đun phụ thuộc chéo, khả năng chạy song song giảm và đồ thị khó hiểu hơn.

Hãy đo thời gian build trước và sau khi tách. So sánh các kịch bản:

- Build sạch toàn bộ.
- Build tăng dần sau một thay đổi nhỏ.
- Chỉ chạy test của mô-đun đang phát triển.
- Build CI trên máy sạch.
- Build khi có cache và khi không có cache.

Số liệu này cho biết việc tách mô-đun có giải quyết đúng nút thắt hay không.

## 13. Tách mô-đun có giúp triển khai độc lập không?

Một mô-đun build riêng không đồng nghĩa với một dịch vụ triển khai độc lập.

Ví dụ, domain, application, web và infrastructure có thể được đóng gói vào cùng một ứng dụng web. Chúng là các mô-đun build riêng nhưng được phát hành như một artifact hoặc một container duy nhất.

Ngược lại, nếu một thành phần được triển khai như một dịch vụ riêng, nó có thể cần:

- Artifact và version riêng.
- API giao tiếp rõ ràng.
- Cấu hình runtime riêng.
- Pipeline kiểm thử và phát hành riêng.
- Quản lý tương thích giữa consumer và provider.

Chia mô-đun build có thể là bước hỗ trợ, nhưng không tự tạo ra ranh giới dịch vụ. Một ứng dụng modular monolith có thể có nhiều mô-đun nhưng vẫn triển khai thành một tiến trình. Đây là lựa chọn hợp lý khi muốn giữ ranh giới mã nguồn rõ mà chưa cần phân tán hệ thống.

## 14. Quản lý version và phát hành mô-đun

Trong một multi-module build, có hai mô hình phổ biến:

### Cùng version

Các mô-đun nội bộ dùng chung một version. Ví dụ:

    domain:1.4.0
    application:1.4.0
    web:1.4.0

Mô hình này đơn giản khi các mô-đun thường được thay đổi và phát hành cùng nhau.

### Version độc lập

Các thư viện có thể có version riêng:

    domain-model:2.3.0
    payment-client:1.8.2
    web-app:5.1.0

Mô hình này phù hợp khi các mô-đun có consumer và vòng đời phát hành khác nhau. Tuy nhiên, nó cần quản lý tương thích, dependency constraints, changelog và quy trình publish chặt chẽ hơn.

Đừng chọn version độc lập chỉ vì công cụ cho phép. Nếu mọi mô-đun luôn được phát hành cùng nhau, version chung thường dễ vận hành hơn.

## 15. Kiểm thử ở cấp mô-đun và kiểm thử tích hợp

Mỗi mô-đun nên có các kiểm thử xác nhận trách nhiệm của nó. Ví dụ:

- domain test quy tắc nghiệp vụ mà không cần database thật.
- application test luồng use case với dependency được thay thế hoặc mô phỏng.
- infrastructure test truy cập database hoặc message broker.
- web test controller, routing và serialization.

Kiểm thử mô-đun không thay thế kiểm thử tích hợp. Khi các mô-đun được ghép lại, vẫn cần xác nhận:

- API giữa các mô-đun tương thích.
- Dependency runtime có đầy đủ.
- Cấu hình ứng dụng hoạt động.
- Tài nguyên và service provider được đóng gói đúng.
- Giao tiếp với database hoặc hệ thống ngoài hoạt động.

Một cấu trúc nhiều mô-đun tốt thường có cả test phạm vi nhỏ và test xác nhận tích hợp ở mức ứng dụng.

## 16. Khi nào không nên tách mô-đun?

Giữ một mô-đun có thể là lựa chọn tốt hơn trong những tình huống sau:

- Dự án còn nhỏ, cấu trúc package đã đủ rõ.
- Các phần thay đổi cùng nhau và không có API ổn định giữa chúng.
- Dependency giữa các phần còn biến động, chưa xác định được ranh giới.
- Build chưa phải nút thắt; tách mô-đun không giải quyết vấn đề đo được.
- Không có nhu cầu tái sử dụng, phát hành hoặc kiểm thử độc lập.
- Nhóm chưa có khả năng duy trì thêm cấu hình và quy trình.

Không nên tách mô-đun chỉ vì:

- Muốn mỗi package có một build.gradle hoặc pom.xml.
- Muốn sơ đồ kiến trúc có nhiều khối hơn.
- Muốn tránh một vài dòng dependency.
- Muốn chia mã nguồn thành các thư mục có kích thước bằng nhau.
- Dự đoán rằng nhiều mô-đun luôn nhanh hơn.

Nếu ranh giới chưa rõ, hãy tổ chức package, interface và dependency trong một mô-đun trước. Khi trách nhiệm và hướng phụ thuộc ổn định, việc tách build sẽ dễ hơn.

## 17. Những dấu hiệu cho thấy ranh giới mô-đun đang sai

Sau khi tách, cần quan sát xem cấu trúc có thực sự giúp ích không. Các dấu hiệu cảnh báo:

- Dependency vòng giữa các mô-đun.
- Mô-đun chỉ chứa một hoặc hai lớp và không có API có ý nghĩa.
- Nhiều mô-đun phải sửa đồng thời cho hầu hết thay đổi.
- Mô-đun common chứa quá nhiều trách nhiệm không liên quan.
- Consumer phải truy cập lớp implementation nội bộ của mô-đun khác.
- Một mô-đun có dependency vào framework của tầng khác mà không cần thiết.
- Cấu hình build bị sao chép và lệch phiên bản giữa các mô-đun.
- Build tổng thể vẫn phải chạy lại gần như mọi task sau mỗi thay đổi.

Khi gặp các dấu hiệu này, hãy xem lại ranh giới và dependency graph. Có thể cần gộp mô-đun, tách API, chuyển trách nhiệm hoặc loại dependency không cần thiết. Không phải mọi mô-đun đều phải tồn tại mãi.

## 18. Quy trình chuyển từ một mô-đun sang nhiều mô-đun

Không cần tách toàn bộ dự án trong một lần. Có thể chuyển từng bước:

1. **Đo hiện trạng:** ghi nhận thời gian build, phạm vi test, dependency và những điểm gây khó khăn.
2. **Xác định một ranh giới có giá trị:** chọn thư viện dùng chung hoặc phần có trách nhiệm rõ, ít phụ thuộc ngược.
3. **Xác định API:** quyết định lớp, interface và kiểu dữ liệu nào được phép công khai.
4. **Di chuyển mã nguồn và tài nguyên:** giữ package hợp lý, cập nhật đường dẫn và source set.
5. **Khai báo dependency:** để mô-đun consumer phụ thuộc vào mô-đun provider theo một hướng.
6. **Cập nhật build:** thêm module vào Maven reactor hoặc Gradle settings.
7. **Chạy test riêng và build tổng thể:** xác nhận cả mô-đun và ứng dụng tích hợp đều hoạt động.
8. **Loại bỏ cấu hình trùng:** chuyển version/plugin dùng chung về nơi quản lý tập trung nếu phù hợp.
9. **Đo lại:** so sánh build sạch, build tăng dần và phạm vi kiểm thử.
10. **Lặp lại nếu có lợi ích rõ:** chỉ tách tiếp khi ranh giới mới giải quyết một nhu cầu thực tế.

### Ví dụ chuyển thư viện domain ra riêng

Ban đầu:

    src/main/java/com/example/domain/
    src/main/java/com/example/web/
    src/main/java/com/example/persistence/

Sau khi tách:

    shop/
      domain/
        src/main/java/com/example/domain/
      app/
        src/main/java/com/example/web/
        src/main/java/com/example/persistence/

Mô-đun app khai báo dependency tới domain. Mô-đun domain không phụ thuộc ngược vào app. Các test domain chuyển theo mã nguồn domain và chạy trong task test của mô-đun đó.

Khi di chuyển, cần tìm những lớp ở domain đang import framework web hoặc persistence. Nếu có, có thể đó là dấu hiệu ranh giới trách nhiệm chưa đúng; hãy quyết định chuyển interface hoặc thay đổi hướng dependency trước khi tách.

## 19. Tổ chức cấu hình dùng chung

Khi số mô-đun tăng, việc lặp cấu hình plugin, compiler, test framework và repository có thể gây lệch phiên bản.

Với Maven, parent POM có thể quản lý:

- dependencyManagement.
- pluginManagement.
- properties dùng chung.
- cấu hình compiler và encoding.
- quy tắc kiểm tra chất lượng.

Với Gradle, root build hoặc convention plugins có thể quản lý:

- phiên bản plugin.
- Java toolchain.
- compiler options.
- test framework.
- repository policy.
- quy ước cấu hình cho từng loại mô-đun.

Không nên đưa mọi cấu hình của mọi mô-đun vào một khối root quá lớn. Convention plugin hoặc parent POM có thể giúp chia cấu hình theo loại project, ví dụ library, service hoặc application.

## 20. Dự án nhiều mô-đun và repository nhiều mô-đun khác nhau

Multi-module build có thể nằm trong một repository mã nguồn duy nhất (monorepo). Các mô-đun được build cùng một cấu hình và có thể dùng dependency project nội bộ.

Một mô-đun cũng có thể được tách ra repository riêng nếu cần vòng đời phát triển, quyền truy cập hoặc phát hành độc lập. Tuy nhiên, nhiều repository tạo thêm công việc quản lý version, CI, thay đổi API và đồng bộ dependency.

Hai quyết định này độc lập:

| Quyết định | Câu hỏi |
| --- | --- |
| Tách mô-đun build | Các phần có cần dependency, build và test riêng không? |
| Tách repository Git | Các phần có cần quyền truy cập, nhịp phát hành và quy trình thay đổi độc lập không? |

Có thể bắt đầu bằng một monorepo nhiều mô-đun. Đây thường là cách đơn giản để tạo ranh giới build mà vẫn giữ việc thay đổi API giữa các mô-đun trong cùng một pull request.

## 21. Ví dụ quyết định cho một dự án cụ thể

Giả sử một nhóm phát triển hệ thống bán hàng gồm API web, quy tắc đơn hàng và truy cập database. Hiện tại toàn bộ mã nguồn nằm trong một mô-đun.

Các vấn đề:

- Domain test phải kéo theo nhiều dependency web và database.
- Hai ứng dụng khác cũng cần dùng quy tắc tính giá.
- Mã domain thường xuyên bị sửa cùng mã controller.
- Build vẫn nhanh và cả hệ thống luôn được phát hành cùng nhau.

Có thể tách domain thành mô-đun thư viện nếu API quy tắc giá đã ổn định và có consumer thứ hai. Việc tách có thể giảm dependency không cần thiết và cho phép test domain độc lập.

Nhưng chưa chắc cần tách web và infrastructure thành hai mô-đun ngay. Nếu chúng luôn được triển khai cùng nhau, thay đổi cùng nhau và không có nhu cầu kiểm thử/build độc lập, có thể giữ chúng trong mô-đun ứng dụng cho đến khi xuất hiện nhu cầu rõ hơn.

Quyết định hợp lý có thể là:

    shop/
      domain/
      application/

Trong đó application vẫn chứa web và infrastructure. Sau khi đo hiệu quả và ổn định API, nhóm có thể cân nhắc tách tiếp.

## 22. Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là Có | Hướng cân nhắc |
| --- | --- | --- |
| Một phần được nhiều ứng dụng dùng chung? | Có consumer độc lập. | Tách thành library module. |
| Phần đó có API và trách nhiệm ổn định? | Có ranh giới rõ. | Mô-đun riêng có thể phù hợp. |
| Cần build/test phần đó độc lập? | Có nhu cầu thường xuyên. | Tách build module. |
| Cần version/publish riêng? | Có vòng đời artifact riêng. | Tách mô-đun có artifact riêng. |
| Dependency giữa hai phần có hướng rõ? | Có thể tạo DAG. | Có cơ sở để tách. |
| Hai phần luôn thay đổi và phát hành cùng nhau? | Ít lợi ích độc lập. | Có thể giữ chung. |
| Có dependency vòng hoặc truy cập nội bộ chéo? | Ranh giới chưa ổn định. | Thiết kế lại trước khi tách. |
| Build đang chậm nhưng mọi phần phụ thuộc lẫn nhau? | Tách đơn thuần chưa chắc giúp. | Đo và sửa dependency graph trước. |

## 23. Nguyên tắc thực hành

- Bắt đầu từ trách nhiệm và dependency, không bắt đầu từ số lượng thư mục.
- Tách mô-đun khi có lợi ích đo được về build, test, tái sử dụng, dependency hoặc phát hành.
- Giữ hướng phụ thuộc rõ ràng và tránh chu trình.
- Công khai API tối thiểu; giữ implementation detail bên trong mô-đun.
- Không biến mô-đun common thành nơi chứa mọi lớp chưa phân loại.
- Quản lý version plugin và dependency dùng chung tập trung.
- Có test ở cấp mô-đun và test tích hợp ở cấp ứng dụng.
- Đo thời gian build trước và sau khi tách.
- Phân biệt mô-đun build với package Java, JPMS module và dịch vụ triển khai.
- Không tách repository Git nếu nhu cầu quyền truy cập hoặc vòng đời phát hành chưa đòi hỏi.

Chia một dự án thành nhiều mô-đun build là cách tạo ranh giới có thể được công cụ build thực thi: dependency nào được phép, task nào cần chạy, test nào thuộc phần nào và artifact nào được tạo. Quyết định có giá trị khi ranh giới đó phản ánh trách nhiệm ổn định và giải quyết một nhu cầu thực tế. Nếu không có lợi ích rõ ràng, một mô-đun với package được tổ chức tốt vẫn là cấu trúc đơn giản và hiệu quả.
