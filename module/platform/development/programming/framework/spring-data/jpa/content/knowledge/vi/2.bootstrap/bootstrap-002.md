# Quản lý phiên bản Spring Boot, Spring Data và Hibernate bằng BOM

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích BOM quản lý phiên bản dependency như thế nào và vì sao cần đồng bộ các thư viện trong một ứng dụng Spring Data JPA.
- Chọn đúng BOM khi dự án dùng Spring Boot hoặc dùng Spring Data độc lập.
- Cấu hình BOM bằng Maven hoặc Gradle.
- Kiểm tra phiên bản thực tế được chọn và xử lý xung đột dependency có căn cứ.

## 1. Vì sao phải quản lý phiên bản đồng bộ?

Một ứng dụng dùng Spring Data JPA thường có nhiều lớp thư viện liên quan:

- Spring Boot cung cấp cấu hình tự động, starter và tập hợp dependency đã được kiểm thử cùng nhau.
- Spring Data JPA cung cấp repository, abstraction và cách truy cập dữ liệu theo mô hình Spring Data.
- Spring Framework cung cấp các nền tảng như dependency injection, transaction và tích hợp ORM.
- Hibernate thường là JPA provider thực thi thao tác persistence.
- Jakarta Persistence cung cấp API chuẩn mà Spring Data JPA và Hibernate cùng sử dụng.

Các thành phần này tương tác ở cả thời điểm biên dịch lẫn lúc chạy. Một phiên bản Hibernate quá mới hoặc quá cũ so với Spring Boot và Spring Data có thể khiến ứng dụng không khởi động, lỗi khi tạo EntityManagerFactory, lỗi liên kết phương thức hoặc lỗi khi thực thi truy vấn.

Ví dụ, một dự án có thể biên dịch thành công nhưng gặp lỗi NoSuchMethodError khi chạy. Lỗi này thường cho thấy một thư viện đang gọi API không tồn tại trong phiên bản thư viện thực tế được nạp. Nguyên nhân có thể là dependency trực tiếp đã ghi đè phiên bản mà BOM quản lý.

Nguyên tắc an toàn là chọn một bộ phiên bản đã được kiểm thử tương thích và để một nguồn quản lý phiên bản điều phối các dependency liên quan. Khi dự án dùng Spring Boot, nguồn đó thường là Spring Boot BOM.

## 2. BOM là gì?

BOM là viết tắt của Bill of Materials. Trong hệ sinh thái Maven, BOM là một POM có packaging là pom, chứa các quy tắc quản lý phiên bản trong phần dependencyManagement.

BOM giúp dự án khai báo phiên bản của một nhóm thư viện tại một nơi. Khi dependency được khai báo mà không ghi version, công cụ build có thể lấy phiên bản đã được BOM quản lý.

Cần phân biệt hai phần:

- dependencies: khai báo thư viện mà module thực sự cần dùng.
- dependencyManagement: quy định phiên bản mặc định và một số thuộc tính quản lý cho dependency khi module khai báo thư viện đó.

Import một BOM không tự động thêm tất cả thư viện trong BOM vào classpath. BOM chỉ cung cấp quy tắc quản lý. Module vẫn phải khai báo những dependency mà nó sử dụng.

### Các BOM liên quan

| BOM | Phạm vi quản lý | Khi nên dùng |
|---|---|---|
| Spring Boot BOM: spring-boot-dependencies | Các dependency được Spring Boot tuyển chọn, bao gồm Spring Framework, Spring Data và Hibernate theo từng bản Spring Boot | Ứng dụng sử dụng Spring Boot |
| Spring Data BOM: spring-data-bom | Các module Spring Data thuộc cùng một release train | Dự án dùng Spring Data nhưng không dùng Spring Boot, hoặc cần quản lý nhiều module Spring Data độc lập |
| Hibernate platform BOM: hibernate-platform | Các module thuộc Hibernate ORM cùng một dòng phiên bản | Dự án khai báo nhiều module Hibernate trực tiếp và cần đồng bộ chúng |

Không nên import nhiều BOM có phạm vi chồng lấn chỉ để ép từng thư viện về một phiên bản riêng. Nếu dự án dùng Spring Boot, hãy bắt đầu từ Spring Boot BOM. Chỉ bổ sung quy tắc ghi đè khi có lý do cụ thể và đã kiểm tra tính tương thích.

## 3. Cấu hình Spring Boot BOM bằng Maven

Có hai cách phổ biến. Chọn một cách phù hợp với cấu trúc POM của dự án.

### Cách A: Kế thừa spring-boot-starter-parent

Nếu dự án có thể dùng Spring Boot làm parent, khai báo parent ở POM gốc:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>
~~~

Phiên bản 3.5.0 chỉ minh họa cú pháp. Hãy thay bằng phiên bản Spring Boot đã được dự án lựa chọn và còn phù hợp với Java cùng các thư viện đang sử dụng.

Sau đó khai báo starter mà không cần ghi version:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Starter đưa các dependency cần thiết cho Spring Data JPA vào dự án. Spring Boot BOM quản lý phiên bản của các thành phần tương ứng. Thông thường, bạn không cần khai báo riêng version cho spring-data-jpa hoặc hibernate-core.

Spring Boot parent còn cung cấp cấu hình mặc định và quản lý plugin Maven. Đây là lựa chọn thuận tiện nếu dự án không bị ràng buộc bởi một parent POM khác.

### Cách B: Import spring-boot-dependencies

Nếu tổ chức đã có parent POM riêng, không thể kế thừa Spring Boot parent, hãy import BOM trong dependencyManagement:

~~~xml
<properties>
    <spring-boot.version>3.5.0</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Điểm quan trọng:

1. BOM phải nằm trong dependencyManagement.
2. type phải là pom.
3. scope phải là import.
4. Version BOM được đặt tại một property để có thể nâng cấp tập trung.
5. Dependency sử dụng trong module vẫn phải nằm trong dependencies.

Cách import BOM phù hợp khi dự án có parent POM riêng hoặc muốn kiểm soát rõ ràng phần quản lý dependency. Tuy nhiên, import BOM không tự cung cấp toàn bộ cấu hình plugin mà Spring Boot parent có thể cung cấp.

### Quản lý trong dự án Maven nhiều module

Với dự án nhiều module, nên đặt BOM tại POM gốc để các module con dùng chung một bộ phiên bản.

~~~xml
<!-- POM gốc -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Module cần JPA chỉ khai báo dependency:

~~~xml
<!-- POM của module persistence -->
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Cách này giúp các module không tự chọn những phiên bản Spring Data hoặc Hibernate khác nhau. Nếu một module cần ghi version riêng, hãy xem đó là một thay đổi có chủ đích và kiểm tra ảnh hưởng đến toàn bộ dependency graph.

## 4. Cấu hình BOM bằng Gradle

Gradle hỗ trợ BOM thông qua platform. Ví dụ dưới đây sử dụng cơ chế BOM gốc của Gradle:

~~~groovy
plugins {
    id 'java'
}

ext {
    springBootVersion = '3.5.0'
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}"))

    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
~~~

Thay phiên bản minh họa bằng phiên bản Spring Boot mà dự án đã chọn. Khi platform được import, các dependency được BOM quản lý có thể được khai báo mà không cần ghi version riêng.

Nếu dự án đang sử dụng plugin io.spring.dependency-management, có thể import BOM theo cách sau:

~~~groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.0'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
~~~

Hai ví dụ trên thể hiện hai cơ chế quản lý BOM khác nhau. Hãy dùng cơ chế phù hợp với cấu hình hiện tại của dự án, tránh khai báo lặp cùng một BOM theo nhiều cách.

Gradle có cả platform và enforcedPlatform:

- platform đưa các constraint từ BOM vào quá trình giải quyết dependency.
- enforcedPlatform ép các phiên bản trong BOM được áp dụng mạnh hơn, kể cả khi dependency khác đưa ra yêu cầu khác.

Chỉ dùng enforcedPlatform khi dự án thực sự cần quy tắc ép phiên bản và đã đánh giá ảnh hưởng đến các thư viện khác. Với ứng dụng thông thường, platform là điểm bắt đầu phù hợp hơn.

## 5. Khi dự án không sử dụng Spring Boot

Nếu dự án dùng Spring Data độc lập, Spring Data BOM giúp các module Spring Data cùng thuộc một release train.

Ví dụ import Spring Data BOM bằng Maven:

~~~xml
<properties>
    <spring-data.release>2025.0.0</spring-data.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>${spring-data.release}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Phiên bản 2025.0.0 chỉ minh họa cấu trúc. Hãy chọn release train phù hợp với phiên bản Spring Framework, Java và các module Spring Data của dự án. Không lấy một release train bất kỳ chỉ vì nó có số phiên bản mới hơn.

Nếu dự án khai báo nhiều thành phần Hibernate trực tiếp, Hibernate platform BOM có thể giúp các module Hibernate cùng phiên bản:

~~~xml
<properties>
    <hibernate.version>6.6.15.Final</hibernate.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-platform</artifactId>
            <version>${hibernate.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Artifact và phiên bản của Hibernate platform cần khớp với dòng Hibernate mà dự án chọn. Hãy kiểm tra tài liệu của đúng major version trước khi sử dụng.

Spring Data BOM quản lý các module Spring Data; Hibernate platform BOM quản lý các module Hibernate. Hai BOM này không tự đảm bảo rằng một phiên bản Spring Data bất kỳ sẽ tương thích với một phiên bản Hibernate bất kỳ. Khi không có Spring Boot điều phối, nhóm phát triển phải chọn phiên bản Spring Framework, Spring Data, Hibernate và Jakarta Persistence theo ma trận tương thích của các dự án tương ứng.

## 6. Có nên ghi đè phiên bản do BOM quản lý?

Mặc định, không ghi version trực tiếp cho dependency đã được BOM quản lý. Ví dụ, nếu Spring Boot BOM đang quản lý Hibernate, không nên thêm một version tùy ý vào dependency hibernate-core.

Chỉ cân nhắc ghi đè khi có lý do rõ ràng, chẳng hạn:

- Cần bản vá bảo mật mà phiên bản Spring Boot hiện tại chưa quản lý.
- Cần sửa một lỗi đã được xác định trong dependency.
- Có yêu cầu tương thích cụ thể từ thư viện hoặc nền tảng triển khai.

Quy trình an toàn:

1. Kiểm tra bản Spring Boot mới hơn có cập nhật dependency cần thiết hay chưa. Ưu tiên nâng cấp Spring Boot patch release phù hợp.
2. Đọc release notes và ma trận tương thích của Spring Boot, Spring Data và Hibernate.
3. Nếu vẫn cần ghi đè, chỉ sử dụng property override được BOM của phiên bản đang dùng hỗ trợ hoặc khai báo dependencyManagement rõ ràng.
4. Kiểm tra effective POM hoặc dependency insight để xác nhận phiên bản thực tế.
5. Chạy build, test repository, test transaction và các integration test liên quan đến persistence.

Một số phiên bản Spring Boot cung cấp property để điều chỉnh phiên bản dependency do BOM quản lý. Tên property phụ thuộc vào BOM cụ thể. Ví dụ, có thể gặp property hibernate.version trong một số dòng Spring Boot. Hãy xác nhận property đó có tồn tại trong BOM của dự án trước khi ghi đè; không tự đoán tên property.

Một dependency khai báo version trực tiếp có thể làm thay đổi kết quả quản lý phiên bản. Vì vậy, khi thấy một thư viện không dùng phiên bản mong đợi, hãy tìm cả dependency trực tiếp lẫn dependency bắc cầu đang yêu cầu phiên bản đó.

## 7. Lưu ý về Java và namespace Jakarta

Phiên bản thư viện phải phù hợp với nền tảng Java và namespace persistence mà ứng dụng sử dụng.

- Spring Boot 3 trở lên sử dụng Jakarta EE APIs, trong đó JPA dùng package jakarta.persistence.
- Các ứng dụng Spring Boot 2 cũ thường dùng package javax.persistence.
- Spring Boot 3 yêu cầu Java 17 trở lên.

Không trộn entity hoặc thư viện biên dịch theo javax.persistence với stack Jakarta của Spring Boot 3+. Khi nâng cấp từ Boot 2 lên Boot 3, cần rà soát import, dependency, plugin và thư viện tích hợp JPA, không chỉ thay số phiên bản Hibernate.

## 8. Kiểm tra phiên bản thực tế

Không nên chỉ nhìn file POM hoặc build.gradle rồi kết luận dependency đã được đồng bộ. Cần kiểm tra kết quả giải quyết dependency của công cụ build.

### Maven

Xem POM sau khi áp dụng parent và BOM:

~~~bash
./mvnw help:effective-pom
~~~

Xem dependency tree liên quan:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.data,org.hibernate.orm
~~~

Đọc kết quả và xác nhận:

- spring-boot-starter-data-jpa dùng bộ phiên bản do Spring Boot quản lý.
- Các module org.springframework.data thuộc release train tương thích.
- org.hibernate.orm:hibernate-core có một phiên bản được chọn rõ ràng.
- Không có dependency trực tiếp vô tình ghi đè phiên bản mà dự án mong muốn.

### Gradle

Xem toàn bộ dependency của runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do Gradle chọn phiên bản Spring Data JPA:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

Tìm lý do Gradle chọn phiên bản Hibernate:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

dependencyInsight giúp xác định dependency nào yêu cầu một phiên bản, constraint nào được áp dụng và vì sao Gradle chọn phiên bản cuối cùng.

Sau khi xác nhận dependency tree, chạy build và các test persistence. Một dependency tree sạch là điều kiện cần, nhưng không thay thế kiểm thử chức năng.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Một module Spring Data có phiên bản khác các module còn lại | Ghi version trực tiếp hoặc dùng nhiều release train | Bỏ version riêng và quản lý bằng cùng một BOM |
| Hibernate có phiên bản ngoài dự kiến | Dependency bắc cầu hoặc dependencyManagement khác ghi đè | Dùng dependency tree hoặc dependencyInsight để tìm nguồn yêu cầu |
| NoSuchMethodError hoặc NoClassDefFoundError | Các thư viện không tương thích ở runtime | Kiểm tra phiên bản được chọn, đồng bộ BOM và chạy lại integration test |
| Ứng dụng không tạo được EntityManagerFactory | Hibernate, JPA API hoặc cấu hình persistence không tương thích | Kiểm tra stack trace, Hibernate version, Jakarta API và cấu hình datasource |
| Import jakarta.persistence không tìm thấy | Dự án đang dùng stack cũ hoặc dependency chưa được nâng cấp đồng bộ | Kiểm tra phiên bản Spring Boot và dependency JPA |
| Import javax.persistence không tìm thấy sau nâng cấp | Mã nguồn vẫn dùng namespace cũ | Chuyển import và thư viện liên quan sang Jakarta khi dùng Boot 3+ |

Một số lỗi có thể đến từ cấu hình datasource, mapping entity hoặc transaction chứ không phải BOM. Hãy dùng stack trace và dependency tree để phân biệt nguyên nhân, tránh thay phiên bản theo cảm tính.

## 10. Quy trình nâng cấp phiên bản đề xuất

Khi nâng cấp Spring Boot, Spring Data hoặc Hibernate:

1. Xác định phiên bản Spring Boot mục tiêu và phiên bản Java tối thiểu tương ứng.
2. Đọc release notes để biết thay đổi của Spring Data, Hibernate, Spring Framework và Jakarta APIs.
3. Nâng BOM tại một vị trí quản lý tập trung.
4. Xóa các version riêng đã trở nên dư thừa, trừ những override có chủ đích.
5. Chạy dependency tree hoặc dependencyInsight để xem các phiên bản thực tế.
6. Chạy build và test, đặc biệt là repository, mapping, transaction, pagination, locking và truy vấn tùy chỉnh.
7. Ghi lại lý do nếu phải giữ một dependency override để lần nâng cấp sau có thể đánh giá lại.

Tránh sử dụng phiên bản động như latest.release hoặc dấu cộng trong Gradle cho dependency production. Phiên bản động có thể khiến cùng một commit giải quyết ra dependency khác nhau ở những thời điểm khác nhau. Hãy dùng phiên bản BOM cụ thể và cơ chế khóa dependency nếu quy trình build của dự án yêu cầu tái lập tuyệt đối.

## Checklist trước khi merge

- [ ] Dự án xác định rõ BOM chính đang quản lý dependency.
- [ ] Spring Boot, Spring Data và Hibernate thuộc các phiên bản tương thích.
- [ ] Dependency đã được BOM quản lý không bị ghi version tùy tiện ở module con.
- [ ] Các module Spring Data dùng cùng release train.
- [ ] Không trộn javax.persistence và jakarta.persistence.
- [ ] Dependency tree hoặc dependencyInsight đã được kiểm tra.
- [ ] Build và integration test liên quan đến JPA đã chạy thành công.
- [ ] Mọi version override đều có lý do, nguồn tương thích và test xác nhận.

## Kết luận

Với ứng dụng Spring Data JPA dùng Spring Boot, hãy ưu tiên Spring Boot BOM làm nguồn quản lý phiên bản chung. Khai báo starter mà không ghi version để Spring Boot chọn bộ Spring Data và Hibernate đã được kiểm thử cùng nhau. Chỉ quản lý Spring Data BOM và Hibernate platform BOM riêng khi dự án không dùng Spring Boot hoặc có nhu cầu quản lý độc lập đã được xác định rõ. Luôn xác minh dependency tree và kiểm thử persistence sau mỗi lần thay đổi phiên bản.
