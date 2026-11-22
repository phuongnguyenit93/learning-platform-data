# Chọn bộ phiên bản tương thích giữa Java, Hibernate, Jakarta Persistence và JDBC driver

Trong một ứng dụng Java dùng Hibernate để lưu dữ liệu vào cơ sở dữ liệu quan hệ, việc chọn phiên bản không dừng ở câu hỏi “Hibernate bản mới nhất là bao nhiêu?”. Cần chọn **một bộ phiên bản hoạt động được cùng nhau**: Java runtime, Hibernate ORM, Jakarta Persistence API, JDBC driver và phiên bản database server. Nếu dự án sử dụng Spring Boot, Quarkus hoặc application server, nền tảng đó còn đặt thêm ràng buộc về dependency và vòng đời hỗ trợ.

Bài học này giải thích cách xác định các ràng buộc, đọc ma trận tương thích, chọn bộ phiên bản phù hợp cho dự án mới hoặc dự án đang bảo trì, khai báo dependency bằng Gradle/Maven và nhận diện những lỗi phát sinh khi phối phiên bản sai.

> **Phạm vi thời gian:** các phiên bản minh họa và trạng thái phát hành trong bài được đối chiếu với tài liệu nhà cung cấp vào **15/11/2026**. Các bản vá và chính sách hỗ trợ tiếp tục thay đổi; trước khi nâng cấp hoặc triển khai, hãy xác nhận lại trên trang phát hành chính thức. **Ví dụ dependency là cấu hình minh họa có phiên bản cố định, không phải lời khẳng định chúng luôn là bản mới nhất.**

## 1. Hiểu đúng vai trò của từng thành phần

| Thành phần | Vai trò | Ràng buộc cần kiểm tra |
| --- | --- | --- |
| **Java/JDK/JRE** | Chạy bytecode của ứng dụng và thư viện, cung cấp `java.sql`/`javax.sql` | Mức Java thấp nhất của thư viện, Java được kiểm thử/hỗ trợ, phiên bản dùng biên dịch và chạy |
| **Hibernate ORM** | ORM provider quản lý entity, ánh xạ, SQL, persistence context | Hỗ trợ Java nào, triển khai phiên bản Jakarta Persistence nào, tương thích database/dialect và framework nào |
| **Jakarta Persistence API** | Chuẩn API `jakarta.persistence.*` cho entity, `EntityManager`, JPQL... | Phiên bản đặc tả mà Hibernate provider triển khai, namespace API, yêu cầu của framework/application server |
| **JDBC API** | API kết nối/query chuẩn thuộc JDK, ví dụ `Connection`, `PreparedStatement` | Mức JDBC do JDK cung cấp; các khả năng JDBC mà driver thực sự hỗ trợ |
| **JDBC driver** | Triển khai kết nối tới một loại cơ sở dữ liệu nhất định | Java tối thiểu, database server được hỗ trợ, protocol, TLS/authentication, mức JDBC thực hiện |
| **Database server** | Cơ sở dữ liệu thực sự lưu và truy vấn dữ liệu | Phiên bản server, kiểu dữ liệu, cú pháp SQL/dialect, tính năng driver và ORM hỗ trợ |
| **Framework/container (nếu có)** | Quản lý dependency, datasource, transaction và tích hợp JPA | Phiên bản Hibernate/Jakarta Persistence do BOM hoặc runtime cung cấp |

Một luồng phổ biến:

```text
Ứng dụng (biên dịch và chạy bằng Java đã chọn)
  └─ Jakarta Persistence API
      └─ Hibernate ORM (provider thực thi API)
          └─ JDBC API của Java + JDBC driver của hãng CSDL
              └─ PostgreSQL / MySQL / Oracle / SQL Server / ...

Nếu dùng Spring Boot:
Ứng dụng → Spring Data JPA / EntityManager → Hibernate → JDBC driver → database
                    ↑
              Spring Boot BOM quản lý nhiều phiên bản phụ thuộc
```

**Không được đánh đồng các số phiên bản**: Hibernate `7.x` không có nghĩa cần Jakarta Persistence `7.x`; Jakarta Persistence `3.2` không phải JDBC `3.2`; PostgreSQL JDBC driver `42.7.x` cũng không liên quan tới Hibernate `7.x` theo cách đánh số.

## 2. Tương thích là giao của nhiều điều kiện

Một bộ công nghệ chỉ có thể được chọn khi đồng thời thỏa mãn các điều kiện:

```text
Java runtime hỗ trợ Hibernate
            ∩
Hibernate triển khai Jakarta Persistence API dự kiến
            ∩
JDBC driver chạy được trên Java runtime
            ∩
JDBC driver hỗ trợ database server
            ∩
Hibernate hỗ trợ dialect/version của database
            ∩
Framework/container (nếu dùng) cho phép tổ hợp này
            =
         Bộ phiên bản có thể sử dụng
```

Sau khi đáp ứng điều kiện kỹ thuật còn cần xem xét **trạng thái bảo trì**, bản vá bảo mật, lịch nâng cấp và khả năng chạy kiểm thử tích hợp. “Chương trình khởi động được” chưa chứng minh mọi tính năng, kiểu dữ liệu, transaction và migration đều tương thích.

### 2.1. Ba khái niệm dễ bị nhầm

1. **Java tối thiểu để chạy:** thư viện được biên dịch cho một mức class-file nhất định. Java runtime cũ hơn không thể nạp các lớp đòi hỏi class-file mới.
2. **Java được hỗ trợ/kiểm thử:** danh sách JDK mà nhà cung cấp công bố. Một JDK ngoài danh sách có thể chạy một số trường hợp nhưng chưa được bảo đảm trong ma trận công khai.
3. **Java dùng để build chính Hibernate:** có thể khác Java runtime cần để chạy artifact đã phát hành. Đọc mục yêu cầu đối với **artifact/ứng dụng**, đừng nhầm với yêu cầu dành cho người đóng góp xây Hibernate từ mã nguồn.

Tương tự, **JDBC API level** và **phiên bản driver** là hai thông số khác nhau. Ví dụ, Java 21 có các JDBC API của JDK hiện đại, nhưng một driver công bố triển khai JDBC 4.2 có thể chưa cung cấp đầy đủ các lời gọi bổ sung của JDBC 4.3. Nó vẫn có thể chạy trên Java 21 nếu nhà cung cấp xác nhận hỗ trợ JDK này và ứng dụng chỉ dùng các khả năng được driver triển khai.

## 3. Ma trận Java – Hibernate – Jakarta Persistence

Hibernate công bố các phiên bản Java và Jakarta Persistence tương thích theo **dòng phát hành**. Bảng dưới đây dựa trên [Hibernate ORM releases](https://hibernate.org/orm/releases/) và trang từng dòng phát hành tại thời điểm 15/11/2026:

| Dòng Hibernate ORM | Java được liệt kê trong ma trận chính thức | Jakarta Persistence | Trạng thái phát hành tại thời điểm đối chiếu |
| --- | --- | --- | --- |
| **7.4** | 17, 21, 25, 26 | **3.2** | Latest stable |
| **7.2** | 17, 21, 25 | **3.2** | Limited support |
| **6.6** | 11, 17, 21; Java 25 từ 6.6.40+, Java 26 từ 6.6.49+ | **3.1** | Limited support |
| **8.0** | Dòng phát triển, chưa chọn làm mặc định cho production | **4.0** | Development, không xem là dòng stable |

Nguồn trực tiếp: [Hibernate 7.4](https://hibernate.org/orm/releases/7.4/), [Hibernate 7.2](https://hibernate.org/orm/releases/7.2/), [Hibernate 6.6](https://hibernate.org/orm/releases/6.6/).

**Cách đọc đúng:**

- Nếu tổ chức phải chạy **Java 11**, Hibernate ORM **6.6** là một nhánh được liệt kê hỗ trợ Java 11; không nên tự ghép Hibernate 7.4 vào Java 11.
- Với **Java 17 hoặc Java 21** trong dự án mới, Hibernate **7.4 + Jakarta Persistence 3.2** là một lựa chọn nằm trong ma trận trên, nếu framework/container và database cũng phù hợp.
- Với code và runtime đang ở **Hibernate 6.6 + Jakarta Persistence 3.1**, nâng lên Hibernate 7.x không chỉ là đổi một version: cần kiểm tra API, mapping, query và migration guide.
- Nếu đang dùng Java 25/26, lưu ý điều kiện **bản vá tối thiểu trong dòng Hibernate 6.6**. Chỉ nhìn `6.6` mà bỏ qua `.40+` hoặc `.49+` dễ dẫn tới kết luận sai.
- Một dòng phát hành có thể bị hạ mức hỗ trợ sau này. Ưu tiên chính sách bảo trì chính thức và đường nâng cấp đã được kiểm thử thay vì tự chọn phiên bản cao nhất.

> Dữ liệu ma trận là **những phiên bản Java được nhà cung cấp nêu rõ**, không có nghĩa mọi số Java nằm giữa đều mặc nhiên nhận cùng mức hỗ trợ. Khi có nhu cầu dùng JDK khác, hãy đọc lại compatibility policy, release notes và kết quả kiểm thử hiện hành.

## 4. Chọn Jakarta Persistence theo Hibernate, không chọn độc lập

Jakarta Persistence được cung cấp dưới dạng API artifact thường gặp:

```text
jakarta.persistence:jakarta.persistence-api:<version>
```

Hibernate ORM thường dùng dependency:

```text
org.hibernate.orm:hibernate-core:<version>
```

Mỗi Hibernate provider triển khai một mức Jakarta Persistence cụ thể. Với các dòng đang minh họa:

```text
Hibernate ORM 6.6   → Jakarta Persistence 3.1
Hibernate ORM 7.2   → Jakarta Persistence 3.2
Hibernate ORM 7.4   → Jakarta Persistence 3.2
```

Không nên khai báo `jakarta.persistence-api:3.2` một cách độc lập rồi giữ Hibernate 6.6 chỉ vì muốn có “API mới nhất”: code có thể biên dịch khi thấy method mới nhưng provider 6.6 không cam kết triển khai hành vi Jakarta Persistence 3.2. Ngược lại, ép API 3.1 trong khi provider được xây cho 3.2 có thể thiếu interface/method mà provider kỳ vọng và gây lỗi khi khởi động hoặc gọi tính năng.

Một lưu ý đặc biệt đối với hệ thống cũ: **`javax.persistence.*` và `jakarta.persistence.*` là hai namespace khác nhau**, không thể sửa bằng cách tăng version ngẫu nhiên. Jakarta Persistence 3.x dùng `jakarta.persistence.*`; nhiều ứng dụng dựa trên JPA 2.x dùng `javax.persistence.*`. Việc nâng Hibernate và Jakarta Persistence có thể cần thay import, cấu hình và dependency liên quan trong toàn bộ ứng dụng.

```java
// Entity theo Jakarta Persistence 3.x
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    private Long id;

    protected Product() {}
}
```

`java.sql.Connection` và `javax.sql.DataSource` **vẫn giữ package của Java/JDBC**, không đổi thành `jakarta.sql.*`.

## 5. Chọn JDBC driver: kiểm tra cả Java lẫn database server

Hibernate và Jakarta Persistence không thay thế JDBC driver. Mỗi DBMS có driver phù hợp với giao thức của nó. Khi lựa chọn, luôn tra **tài liệu driver của nhà cung cấp** theo ít nhất bốn chiều:

1. **JDK runtime tối thiểu / JDK được kiểm thử.** Một driver biên dịch cho Java mới hơn runtime thực tế có thể gây `UnsupportedClassVersionError`.
2. **Database server tương thích.** Driver mới có thể ngừng hỗ trợ giao thức hoặc server cũ; driver cũ có thể không hiểu authentication hay đặc tính của server mới.
3. **Tính năng JDBC và vendor-specific.** Kiểm tra hỗ trợ `java.time`, generated keys, batch, transaction, kiểu JSON/ARRAY, streaming và timeout nếu ứng dụng cần.
4. **TLS, authentication, chính sách vá lỗi.** Chọn release còn được bảo trì và đáp ứng hạ tầng bảo mật, tránh giữ driver cũ chỉ vì kết nối thử thành công.

### 5.1. Ví dụ với PostgreSQL

Driver PostgreSQL phổ biến có coordinates:

```text
org.postgresql:postgresql:<version>
```

Theo [trang tải pgJDBC](https://jdbc.postgresql.org/download/) tại thời điểm đối chiếu, bản **42.7.14** yêu cầu **Java 8 trở lên** và cung cấp biến thể JDBC 4.2 cho Java 8+. Tài liệu cũng lưu ý driver mới không còn bảo đảm hoạt động với các PostgreSQL server quá cũ; do đó phải xem cả version server, không chỉ JDK.

Một dự án Java 21 dùng Hibernate 7.4, Jakarta Persistence 3.2 và PostgreSQL có thể chọn `org.postgresql:postgresql:42.7.14`, rồi xác nhận phiên bản PostgreSQL server hiện có được pgJDBC và Hibernate hỗ trợ. **Số `42.7.14` là số phát hành của driver, không phải JDBC API 42.7.14.**

### 5.2. Ví dụ với MySQL

Driver chính thức dùng coordinates:

```text
com.mysql:mysql-connector-j:<version>
```

Theo [MySQL Connector/J compatibility guide](https://dev.mysql.com/doc/connector-j/en/connector-j-versions.html), tại thời điểm đối chiếu dòng Connector/J **26.10** công bố chạy trên **JRE 8+**, triển khai **JDBC 4.2** và hỗ trợ **MySQL Server 8.4+**. Đây là ví dụ rõ ràng rằng **phiên bản server quyết định lựa chọn driver**; không thể chỉ suy từ JDK rằng driver sẽ tương thích với mọi MySQL server cũ.

### 5.3. Với Oracle Database hoặc SQL Server

- **Oracle JDBC:** ngoài version, nhà cung cấp thường có biến thể artifact theo mức JDK, ví dụ các tên `ojdbc...`; chọn theo bảng hỗ trợ Java–Oracle Database và hướng dẫn driver chính thức, kiểm tra xác thực/TLS.
- **Microsoft SQL Server JDBC:** một số artifact có classifier hoặc cách phát hành chỉ rõ JRE mục tiêu; xem bảng tương thích giữa driver release, JDK và SQL Server/Azure SQL, đồng thời kiểm tra TLS/encryption.

Không áp dụng phiên bản PostgreSQL hoặc MySQL ở ví dụ trên cho các DBMS khác. Driver khác hãng không phải phần mềm thay thế ngang hàng cho nhau.

## 6. Cân nhắc database dialect và schema

Tổ hợp “Java + Hibernate + Jakarta Persistence + driver” vẫn có thể không vận hành đúng khi **phiên bản database** nằm ngoài phạm vi được ORM hỗ trợ. Hibernate dùng thông tin dialect để sinh SQL, lựa chọn cú pháp phân trang, kiểu dữ liệu, identity/sequence, khóa và các biểu thức có tính đặc thù DBMS.

Ví dụ, hai PostgreSQL server khác đời có thể khác khả năng hỗ trợ kiểu dữ liệu hoặc các chức năng SQL; một driver bắt tay kết nối thành công chưa đảm bảo mọi `DDL`, `INSERT`, `SELECT`, pagination và transaction do Hibernate tạo ra đều tương thích.

Khi xác định bộ phiên bản, ghi lại:

```yaml
runtimeJava: 21
hibernateOrm: 7.4.x
jakartaPersistence: 3.2
jdbcDriver: org.postgresql:postgresql:42.7.14
database: PostgreSQL
databaseServer: "phiên bản triển khai thực tế"
platform: "Java SE / Spring Boot / Quarkus / Jakarta EE"
```

Tập dữ liệu này thể hiện đầy đủ các điều kiện cần tra cứu. Không tự điền một phiên bản database chưa được xác nhận. Với hệ thống có nhiều môi trường, kiểm tra cả database staging, production, bản cloud managed và giới hạn nâng cấp của từng nơi.

## 7. Quy trình chọn phiên bản cho dự án mới

### Bước 1 — Chốt Java runtime mục tiêu

Chọn JDK được tổ chức hỗ trợ và phù hợp môi trường triển khai, ví dụ **Java 21**. Phân biệt rõ `java -version` trên máy build, JDK được Gradle/Maven dùng để compile, và `java -version` trong Docker/server. Nếu môi trường chạy Java 17 nhưng code được biên dịch ra class-file Java 21, ứng dụng không khởi động được dù dependency Hibernate hoàn toàn tương thích Java 17.

Đặt Java toolchain hoặc `--release` để kiểm soát đầu ra biên dịch; không chỉ dựa vào phiên bản Java đang được cài trên laptop.

### Bước 2 — Kiểm tra framework/container trước khi chọn Hibernate

Nếu dùng **Spring Boot**, **Quarkus**, **WildFly** hoặc application server khác, mở bảng tương thích và dependency management của **đúng phiên bản framework**. Các nền tảng này thường kiểm thử một tập Hibernate/Jakarta Persistence cụ thể.

Ví dụ ở thời điểm đối chiếu, bảng Hibernate cho thấy **Hibernate ORM 7.4** được liệt kê với **Spring Boot 4.1**; Hibernate **6.6** được liệt kê với **Spring Boot 3.4–3.5**. Điều này không có nghĩa nên đổi Hibernate của một dự án Boot 3.x sang 7.4 bằng một dòng dependency override. Với ứng dụng Spring Boot, thông thường hãy để **BOM/dependency management của Boot chọn phiên bản ORM** trước, rồi thay đổi có chủ đích khi có tài liệu tích hợp chứng minh phù hợp.

### Bước 3 — Chọn dòng Hibernate được bảo trì phù hợp Java

Dùng [ma trận Hibernate ORM](https://hibernate.org/orm/releases/) để xác định dòng tương thích, xem chính sách maintenance và ghi nhận **phiên bản patch** cụ thể. Không chọn `7.+`, `latest.release`, `SNAPSHOT` hoặc version range động cho bản build cần tái hiện.

### Bước 4 — Lấy mức Jakarta Persistence từ ma trận Hibernate

Ví dụ đã chọn Hibernate 7.4 thì dùng API Jakarta Persistence **3.2**, thay vì tự nâng API độc lập. Nếu dùng dependency management của framework, để nó phối hợp API và provider; chỉ khai báo trực tiếp khi cần và tránh tạo phiên bản trùng.

### Bước 5 — Chọn đúng JDBC driver cho database đang dùng

Tra tài liệu driver theo **Java runtime + database server version**. Kiểm tra cả các yêu cầu TLS/authentication và kiểu dữ liệu cụ thể, sau đó chọn bản vá được bảo trì. Không coi “Java 21 chạy được driver” là bằng chứng “driver hỗ trợ database của hệ thống”.

### Bước 6 — Khóa dependency và ghi nhận bộ phiên bản

Khai báo phiên bản cố định hoặc dùng BOM/version catalog/lockfile phù hợp, giữ dependency resolution nhất quán giữa môi trường CI và máy phát triển. Lưu lại Java runtime, phiên bản thực tế của Hibernate/API/driver, database và framework để việc debug sau này có đủ ngữ cảnh.

### Bước 7 — Xác nhận khả năng tích hợp thực tế

Sau khi hoàn thiện bộ phiên bản cho một dự án đang triển khai, cần xác nhận ứng dụng mở được kết nối, tạo được `EntityManagerFactory`, ánh xạ đúng entity, thực thi CRUD và các truy vấn nghiệp vụ có dùng kiểu dữ liệu/transaction đặc biệt. Nếu nâng cấp từ phiên bản cũ, sử dụng migration guide của **từng bước nhảy major/minor** thay vì chỉ kiểm tra việc biên dịch.

## 8. Ví dụ bộ phiên bản và cấu hình Gradle

Giả sử xây dựng một ứng dụng Java SE truy cập PostgreSQL, không dùng Spring Boot. Một bộ phiên bản minh họa tại ngày đối chiếu:

| Thành phần | Lựa chọn minh họa | Cơ sở lựa chọn |
| --- | --- | --- |
| Java | **21** | Có trong Java support matrix của Hibernate 7.4 |
| Hibernate ORM | **7.4.15.Final** | Bản vá ổn định thuộc dòng 7.4, được pin cụ thể để tái hiện build |
| Jakarta Persistence | **3.2.0** | Cùng mức đặc tả mà Hibernate 7.4 triển khai |
| pgJDBC | **42.7.14** | Driver dành cho PostgreSQL, hỗ trợ Java 8+ |
| PostgreSQL server | Phiên bản hiện có, đã xác nhận hỗ trợ | Phải tra riêng compatibility của pgJDBC và Hibernate |

Ví dụ `build.gradle` dùng Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'jakarta.persistence:jakarta.persistence-api:3.2.0'
    implementation 'org.hibernate.orm:hibernate-core:7.4.15.Final'

    runtimeOnly 'org.postgresql:postgresql:42.7.14'
}
```

Ở ví dụ này, **API được khai báo riêng để nêu rõ hợp đồng lập trình**. Hibernate có thể đã kéo Jakarta Persistence API qua dependency bắc cầu, nên khi tích hợp vào dự án thực tế cần xem dependency tree để tránh các phiên bản trùng. JDBC driver được đặt `runtimeOnly` nếu mã ứng dụng không import trực tiếp lớp `org.postgresql.*`; mọi truy cập JDBC qua các API chuẩn có thể không cần driver ở compile classpath.

Các bản Hibernate đang phát hành có thể nhận patch mới sau ngày đối chiếu. Muốn nâng patch `7.4.15.Final` lên một patch `7.4.x` mới hơn, xem release notes và kiểm thử hồi quy nhưng không tự động đổi major sang `8.x`.

### 8.1. Cấu hình Maven tương ứng

Nếu sử dụng Maven, cùng bộ phiên bản có thể biểu diễn bằng phần `properties` và `dependencies` của `pom.xml`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <hibernate.version>7.4.15.Final</hibernate.version>
    <jakarta.persistence.version>3.2.0</jakarta.persistence.version>
    <postgresql.jdbc.version>42.7.14</postgresql.jdbc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>jakarta.persistence</groupId>
        <artifactId>jakarta.persistence-api</artifactId>
        <version>${jakarta.persistence.version}</version>
    </dependency>
    <dependency>
        <groupId>org.hibernate.orm</groupId>
        <artifactId>hibernate-core</artifactId>
        <version>${hibernate.version}</version>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>${postgresql.jdbc.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây là **đoạn cấu hình**, không phải toàn bộ `pom.xml`. Build Maven cũng cần plugin compiler/toolchain phù hợp để dùng JDK mục tiêu; thuộc tính `maven.compiler.release` kiểm soát mức Java của đầu ra khi Maven Compiler Plugin hỗ trợ nó.

### 8.2. Khai báo entity bằng Jakarta Persistence API đã chọn

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {}  // JPA cần constructor không tham số

    public Book(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

Để chạy, ứng dụng còn cần `persistence.xml` hoặc cấu hình bootstrap tương đương, thông tin JDBC URL/credentials, một bảng `books` phù hợp và ranh giới transaction. Không nên đưa mật khẩu database thật vào mã nguồn hoặc artifact phát hành.

## 9. Ví dụ cấu hình khi dùng Spring Boot

Trong Spring Boot, điểm bắt đầu thường là một **BOM/starter đã được kiểm thử**. Ví dụ ý tưởng sử dụng Gradle:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version-phu-hop>'
    id 'io.spring.dependency-management' version '<dependency-management-version-phu-hop>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Các placeholder trong ví dụ nhắc người học chọn phiên bản Boot/plugin từ tài liệu của chính dòng Boot đang dùng; đoạn trên không phải file build có thể chạy ngay. **Không cần tự thêm `hibernate-core` và `jakarta.persistence-api` với phiên bản tùy ý** khi starter/BOM đã quản lý chúng. Nếu có lý do phải override, đọc compatibility matrix của Spring Boot, Hibernate và release notes tương ứng.

Cũng phải phân biệt **Hibernate ORM** và **Spring Data JPA**: Spring Data JPA là tầng repository; Hibernate ORM thường là provider xử lý mapping/SQL bên dưới. Nâng Spring Data JPA không tự động có nghĩa Hibernate đã hỗ trợ mọi Jakarta Persistence API mới.

## 10. Một số tổ hợp phiên bản: nên dùng, cần kiểm tra, tránh

| Tình huống | Nhận định | Lý do |
| --- | --- | --- |
| Java 21 + Hibernate 7.4 + Jakarta Persistence 3.2 + pgJDBC 42.7.14 | **Có cơ sở tương thích** | Phù hợp các ma trận Java/JPA và driver đã dẫn; còn phải xác nhận PostgreSQL server và framework |
| Java 11 + Hibernate 6.6 + Jakarta Persistence 3.1 + driver hỗ trợ Java 11 | **Có cơ sở tương thích, lưu ý bảo trì** | Hibernate 6.6 hỗ trợ Java 11 nhưng đang trong chế độ limited support tại ngày đối chiếu |
| Java 11 + Hibernate 7.4 | **Không phù hợp ma trận** | Hibernate 7.4 công bố Java 17/21/25/26, không liệt kê Java 11 |
| Java 21 + Hibernate 6.6 + API Jakarta Persistence 3.2 ép độc lập | **Không nên ghép tùy tiện** | Hibernate 6.6 triển khai Jakarta Persistence 3.1, không phải 3.2 |
| Java 21 + Hibernate 7.4 + `javax.persistence` API 2.x | **Sai namespace/đời API** | Hibernate 7.x thuộc hệ `jakarta.persistence.*` |
| Java 21 + Hibernate 7.4 + JDBC driver rất cũ | **Phải kiểm tra kỹ** | Có thể thiếu hỗ trợ DB server/TLS, lỗi authentication, kiểu dữ liệu hoặc đã hết bảo trì |
| Spring Boot 3.x + ép Hibernate 7.4 mà không kiểm tra BOM | **Rủi ro tích hợp** | Tổ hợp Hibernate/Spring Boot cần dựa vào ma trận tích hợp, không chỉ Java và Jakarta Persistence |

Bảng này chỉ là **đánh giá tương thích theo điều kiện đã biết**, không thay cho kết quả kiểm thử ứng dụng và không đảm bảo một hệ thống cụ thể sẽ hoạt động nếu phiên bản DBMS, schema hoặc hạ tầng khác với giả định.

## 11. Khi nào xung đột phiên bản xuất hiện và nhận biết thế nào?

### 11.1. `UnsupportedClassVersionError`

Thông báo thường có dạng “class file version X, runtime chỉ nhận đến Y”. Nguyên nhân có thể là Hibernate/driver hoặc chính ứng dụng được biên dịch cho Java mới hơn runtime thực tế. Kiểm tra JDK chạy ứng dụng, Java toolchain, Docker base image và Java tối thiểu của mọi dependency liên quan.

### 11.2. `NoClassDefFoundError: jakarta/persistence/...`

Có thể thiếu Jakarta Persistence API, dependency bị loại trừ, hoặc classpath đang dùng các JPA `javax.persistence.*` đời cũ. Kiểm tra runtime classpath và namespace, không chỉ sửa import một file.

### 11.3. `NoSuchMethodError`, `AbstractMethodError`, `NoSuchFieldError`

Thường gợi ý vấn đề **không khớp API nhị phân** giữa các JAR khi chạy, ví dụ Hibernate kỳ vọng một method từ dependency mới nhưng runtime nạp phiên bản cũ. Kiểm tra dependency tree, version resolution và JAR thực tế được đóng gói; nguyên nhân cụ thể phải xác nhận bằng stack trace.

### 11.4. `ClassNotFoundException: org.postgresql.Driver` hoặc “No suitable driver”

Có thể thiếu JDBC driver trên runtime classpath, dùng sai JDBC URL hoặc driver không được nạp. Với PostgreSQL URL thường bắt đầu bằng `jdbc:postgresql://...`; với MySQL là `jdbc:mysql://...`. Kiểm tra cả driver dependency, cấu hình datasource và môi trường thực tế.

### 11.5. Lỗi xác thực, TLS, handshake hoặc SQL dialect

Khi ứng dụng đã load class nhưng không kết nối được, cần xem phiên bản server, chính sách xác thực/TLS, cấu hình kết nối, phiên bản driver và network. Nếu đã kết nối được nhưng truy vấn thất bại, kiểm tra SQL do Hibernate sinh, database dialect, schema và tính năng SQL mà server có thể hỗ trợ.

### 11.6. “Chạy được trên máy em, lỗi khi deploy”

Kiểm tra `java -version` ở môi trường chạy, base image, BOM/lockfile, cache dependency, app server có tự cung cấp JPA provider hay không, và có nhiều phiên bản Hibernate/Jakarta Persistence trên classpath hay không. Trên application server có thể xảy ra xung đột classloader nếu ứng dụng đóng gói thêm provider khác với provider do server cung cấp.

## 12. Kiểm tra dependency thực tế bằng công cụ build

Để **xem** dự án đã resolve những JAR nào, thường dùng:

```bash
# Gradle: xem toàn bộ runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Gradle: tìm lý do phiên bản Hibernate được chọn
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath

# Maven: liệt kê dependency thực tế
mvn dependency:tree

# Maven: chỉ tập trung nhóm Hibernate và Jakarta Persistence
mvn dependency:tree -Dincludes=org.hibernate.orm:hibernate-core,jakarta.persistence:jakarta.persistence-api
```

Các lệnh ở đây là **minh họa cách kiểm tra trong dự án**, không phải thao tác đã chạy cho bài học. Đầu ra cần được đọc để xác định dependency nào khai báo phiên bản và có bản transitive nào bị override. Lỗi runtime còn có thể do server/container hoặc file JAR nằm ngoài kết quả cây dependency của module đang kiểm tra.

Các yếu tố cũng nên kiểm tra khi chạy thử một tổ hợp mới:

| Kiểm tra | Mục đích |
| --- | --- |
| `java -version` ở build, test, production | Xác nhận JDK thực sự sử dụng |
| Resolve `hibernate-core` và `jakarta.persistence-api` | Xác nhận cùng dòng đặc tả |
| Resolve JDBC driver | Xác nhận artifact đúng loại database và version được chọn |
| Boot provider/`EntityManagerFactory` | Xác nhận Hibernate khởi tạo được mapping và kết nối |
| CRUD có transaction | Xác nhận đọc, ghi, rollback và sinh khóa hoạt động |
| Query đặc thù và kiểu dữ liệu của hệ thống | Xác nhận dialect/driver phù hợp với database hiện có |
| Migration schema | Xác nhận tương thích DDL/kiểu dữ liệu; dùng công cụ migration có quản lý cho production |
| Integration test trên DBMS thật | Phát hiện khác biệt giữa DB test giả lập và database vận hành |

## 13. Nâng cấp một hệ thống cũ an toàn hơn

Giả sử hệ thống đang chạy **Java 11 + Hibernate 6.6 + Jakarta Persistence 3.1**. Nếu muốn lên dòng Hibernate 7.4, cần lập kế hoạch cho nhiều thay đổi phối hợp:

1. **Khảo sát baseline:** ghi lại Java runtime, Spring Boot/framework (nếu có), Hibernate patch, Jakarta Persistence API, driver, phiên bản database server, thư viện tích hợp Hibernate khác như Search/Validator.
2. **Chọn phiên bản đích:** ví dụ Java 21 + Hibernate 7.4 + Jakarta Persistence 3.2, đồng thời chọn Spring Boot/runtime phù hợp. Kiểm tra chính sách hỗ trợ trước khi quyết định.
3. **Kiểm tra migration guides:** xét các thay đổi về API, entity mapping, HQL/JPQL, dialect, naming strategy, ID generation, schema validation và caching. Đừng coi cập nhật major là chỉ sửa artifact coordinates.
4. **Đồng bộ dependency:** loại những override và API cũ không còn phù hợp; tránh để cả `javax.persistence-api` và `jakarta.persistence-api` xuất hiện do các thành phần tưởng như giống nhau nhưng khác namespace.
5. **Cập nhật JDBC driver có chủ đích:** chọn theo JDK mới **và** database server thực tế, kể cả chuẩn TLS và authentication.
6. **Kiểm thử end-to-end và đo SQL:** thực hiện migration có rollback plan, chạy test CRUD/transaction/query và so sánh log SQL, số query, thời gian phản hồi, hành vi lazy loading và optimistic locking.

Nếu tổ chức vẫn phải giữ Java 11, có thể buộc phải tiếp tục một dòng Hibernate hỗ trợ Java 11 trong giai đoạn chuyển tiếp, nhưng cần nhận thức rõ mức hỗ trợ/bảo trì tại thời điểm triển khai và kế hoạch nâng Java. Không nên nâng độc lập một thành phần để “được version mới” rồi bỏ qua các phụ thuộc khác.

## 14. Lưu hồ sơ quyết định phiên bản cho nhóm phát triển

Một tài liệu ngắn đi cùng dự án giúp người khác hiểu tại sao chọn bộ phiên bản hiện tại:

```markdown
## Persistence stack decision

- Runtime/compile target: Java 21
- Hibernate ORM: 7.4.15.Final
- Jakarta Persistence: 3.2.0
- Database: PostgreSQL <server-version-da-xac-nhan>
- JDBC driver: org.postgresql:postgresql:42.7.14
- Framework/platform: Java SE (không dùng BOM framework)
- Source: Hibernate ORM 7.4 compatibility matrix,
  pgJDBC download/compatibility documentation
- Decision date: 2026-11-15
- Upgrade rule: cập nhật patch sau khi đọc release notes và chạy integration tests
```

Trong dự án thực, thay placeholder bằng phiên bản database đã xác nhận, lưu quyết định vào README/ADR hoặc version catalog, và cập nhật ngày kiểm tra khi thay đổi tổ hợp. Với dự án do framework quản lý dependency, ghi cả **phiên bản framework và BOM** để giải thích nguồn gốc các dependency đã resolve.

## 15. Bài tập tình huống

**Tình huống A.** Máy production chỉ có Java 11; nhóm muốn dùng Hibernate 7.4 và Jakarta Persistence 3.2 ngay mà không đổi runtime. Có phù hợp không?

**Đáp án:** Không theo ma trận đang đối chiếu. Hibernate 7.4 liệt kê Java 17/21/25/26. Nhóm cần nâng Java runtime lên JDK được hỗ trợ, hoặc cân nhắc một dòng Hibernate hỗ trợ Java 11 cùng mức Jakarta Persistence tương ứng, đồng thời xét chính sách bảo trì.

**Tình huống B.** Dự án dùng Java 21, Hibernate 6.6 và Jakarta Persistence 3.1. Lập trình viên tăng riêng Jakarta Persistence lên 3.2 để dùng một API mới. Có đủ không?

**Đáp án:** Không. Hibernate 6.6 được liệt kê triển khai Jakarta Persistence 3.1. Chỉ tăng API có nguy cơ thiếu khả năng thực thi hoặc không khớp classpath; nếu cần tính năng 3.2 phải đánh giá nâng provider và các thành phần phụ thuộc.

**Tình huống C.** Hibernate và Jakarta Persistence đã đúng ma trận, nhưng ứng dụng không kết nối được MySQL server cũ khi nâng driver. Lỗi xuất hiện ở tầng nào trước tiên?

**Đáp án:** Cần kiểm tra tương thích giữa JDBC driver, database server và cơ chế kết nối/xác thực trước, cùng với cấu hình JDBC URL/TLS. Sự tương thích của Hibernate với Java không chứng minh JDBC driver hỗ trợ mọi phiên bản server.

**Tình huống D.** Một dự án Spring Boot khai báo starter JPA rồi tự ép `hibernate-core` sang bản major mới vì IDE gợi ý cập nhật. Nên làm gì?

**Đáp án:** Trước hết tra BOM và ma trận tích hợp của đúng phiên bản Spring Boot. Nếu không có bằng chứng tương thích, ưu tiên nâng framework theo lộ trình được hỗ trợ hoặc giữ bản Hibernate do framework quản lý; kiểm thử tích hợp nếu bắt buộc phải override.

## 16. Tài liệu gốc nên tra khi chọn phiên bản

Các địa chỉ sau là nguồn kiểm tra chính thức; ưu tiên thông tin mới nhất tại thời điểm thực hiện dự án:

- [Hibernate ORM — Releases & compatibility matrix](https://hibernate.org/orm/releases/): Java, Jakarta Persistence, Spring Boot/Quarkus và trạng thái phát hành của từng dòng.
- [Hibernate ORM 7.4](https://hibernate.org/orm/releases/7.4/) và [Hibernate ORM 6.6](https://hibernate.org/orm/releases/6.6/): bảng tương thích chi tiết và liên kết tài liệu/migration.
- [Hibernate ORM — Documentation](https://hibernate.org/orm/documentation/): user guide, migration guide, phiên bản và API liên quan.
- [Jakarta Persistence specification](https://jakarta.ee/specifications/persistence/): phạm vi và phiên bản đặc tả/API.
- [PostgreSQL JDBC Driver — Download & compatibility](https://jdbc.postgresql.org/download/): các bản driver và yêu cầu Java/database.
- [MySQL Connector/J — Compatibility](https://dev.mysql.com/doc/connector-j/en/connector-j-versions.html): ràng buộc Connector/J với Java/JDBC/MySQL server.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): dependency được BOM quản lý; phải chọn đúng tài liệu cho phiên bản Boot sử dụng.

## Kết luận

Hãy chọn phiên bản **từ ngoài vào trong**: chốt Java runtime và framework, chọn dòng Hibernate được hỗ trợ, lấy đúng mức Jakarta Persistence mà Hibernate triển khai, rồi chọn JDBC driver theo **Java và database server thực tế**. Cuối cùng khóa dependency, đọc migration guide khi nâng cấp và xác minh qua bài kiểm tra tích hợp trên database thật. Không có một công thức “luôn dùng phiên bản lớn nhất” có thể thay thế việc đối chiếu cả bộ ràng buộc này.
