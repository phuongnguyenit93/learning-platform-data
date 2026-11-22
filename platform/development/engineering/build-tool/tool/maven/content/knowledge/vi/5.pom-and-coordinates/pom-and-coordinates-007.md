# name, description, url và metadata mô tả dự án trong Maven POM

Một tệp `pom.xml` không chỉ khai báo `groupId`, `artifactId`, `version`, dependency và plugin. Nó còn cho biết **dự án có tên gì để con người nhận ra, giải quyết vấn đề nào, có trang thông tin ở đâu, ai bảo trì, dùng giấy phép gì và tìm mã nguồn hoặc nơi báo lỗi ở đâu**. Những dữ liệu này là *project metadata* (siêu dữ liệu mô tả dự án).

Với một thư viện được người khác sử dụng, metadata chính xác giúp người đọc POM, công cụ tạo báo cáo, kho lưu artifact và các plugin hiểu dự án mà không phải đoán ý nghĩa từ tên tệp JAR. Ba trường mở đầu thường gặp là `<name>`, `<description>` và `<url>`; các nhóm mô tả khác như `<licenses>`, `<developers>` và `<scm>` mở rộng thông tin khi cần.

Bài này tập trung vào các phần tử mô tả trong mô hình POM 4.0.0 của Apache Maven, cách khai báo hợp lệ, ý nghĩa khi build hoặc phát hành và các lỗi dễ mắc khi dùng trong dự án thực tế.

## 1. Phân biệt tọa độ Maven với metadata mô tả

Một artifact Maven thường được nhận diện bằng tọa độ `groupId:artifactId:version`, kèm `packaging` và `classifier` khi tình huống sử dụng yêu cầu. Các phần tử đó giúp Maven giải quyết dependency và chọn đúng artifact. Còn `name`, `description` và `url` phục vụ **việc mô tả và khám phá dự án**.

Ví dụ:

```xml
<groupId>org.example.library</groupId>
<artifactId>order-core</artifactId>
<version>1.2.0</version>

<name>Order Core Library</name>
<description>Thư viện Java cung cấp mô hình đơn hàng.</description>
<url>https://example.org/projects/order-core</url>
```

Các dòng này là **đoạn minh họa bên trong `<project>`**, chưa phải POM độc lập. Trong đó:

| Trường | Trả lời câu hỏi | Tác động chính |
| --- | --- | --- |
| `groupId` | Artifact thuộc nhóm nào? | Một phần của định danh artifact. |
| `artifactId` | Artifact có tên kỹ thuật nào? | Một phần của định danh, tên tệp artifact mặc định. |
| `version` | Đang sử dụng bản phát hành nào? | Chọn phiên bản artifact. |
| `name` | Con người gọi dự án là gì? | Tên hiển thị trong báo cáo, tài liệu và công cụ. |
| `description` | Dự án làm gì, dành cho ai? | Giải thích mục đích bằng văn bản. |
| `url` | Người dùng xem trang chính thức ở đâu? | Liên kết tới trang chủ/tài liệu dự án. |

**Thay `<name>` hoặc `<description>` không tự đổi tọa độ dependency.** Nếu người dùng đã phụ thuộc vào `org.example.library:order-core:1.2.0`, đổi tên hiển thị thành “Order Engine” không khiến Maven tự tìm artifact khác. Ngược lại, đổi `artifactId` là thay đổi có ý nghĩa đối với tọa độ artifact.

Các trường mô tả không quyết định trực tiếp source directory, Java version, dependency graph hay packaging. Tuy nhiên plugin có thể sử dụng metadata để hiển thị báo cáo, xuất POM đã phát hành hoặc thực hiện quy trình riêng của plugin; không nên hiểu “chỉ để mô tả” là “không công cụ nào đọc”.

## 2. `<name>`: tên dễ đọc của dự án

`<name>` là tên dành cho con người. Nó nên rõ nghĩa, đủ ngắn để hiển thị tốt trên trang thông tin và không cần trùng với `artifactId`.

```xml
<artifactId>order-core</artifactId>
<name>Order Core Library</name>
```

Tại đây:

- `order-core` là định danh kỹ thuật dùng trong tọa độ Maven.
- `Order Core Library` là tên có thể xuất hiện trên báo cáo của Maven hoặc trang giới thiệu dự án.

Tên tốt thường cho biết **sản phẩm/thư viện nào** và, khi cần, **vai trò chính**. “Order Core Library” dễ hiểu hơn một tên chung chung như “Java Project” hoặc một chuỗi chỉ gồm mã nội bộ không có ngữ cảnh.

Với dự án nhiều module, mỗi module có thể đặt `name` riêng, ví dụ “Order API”, “Order Domain” và “Order Persistence”, trong khi `artifactId` lần lượt là `order-api`, `order-domain`, `order-persistence`. Tên hiển thị của aggregator/parent cũng nên được đặt cho đúng vai trò của nó.

Lưu ý: `name` không phải namespace Java, tên repository Git hay tên tệp đầu ra. Một số hệ thống downstream có thể dùng nó để tạo tiêu đề, nhưng Maven không coi nó là khóa nhận diện dependency.

## 3. `<description>`: mô tả mục đích của dự án

`<description>` là mô tả **ngắn, cụ thể và phù hợp với phạm vi thật** của module. Một mô tả tốt giúp người đọc phân biệt module này với các module cùng nhóm.

```xml
<description>
    Cung cấp mô hình đơn hàng và các quy tắc kiểm tra
    đầu vào cho ứng dụng thương mại điện tử.
</description>
```

Khi viết mô tả, nên trả lời ba ý nếu phù hợp:

1. **Chức năng chính:** xử lý hoặc cung cấp điều gì?
2. **Ranh giới:** module này sở hữu phần việc nào?
3. **Đối tượng sử dụng:** ứng dụng, dịch vụ hoặc thư viện nào cần nó?

Ví dụ một mô tả chính xác hơn “Useful Java utilities” là:

```xml
<description>Thư viện Java kiểm tra định dạng mã đơn hàng và trạng thái thanh toán.</description>
```

Mô tả không thay thế README, tài liệu API hoặc hướng dẫn cài đặt. Cách dùng thư viện, ví dụ đầu vào/đầu ra, sơ đồ kiến trúc và các quyết định thiết kế dài nên ở tài liệu riêng.

**Vì POM là XML, ký tự đặc biệt phải được escape.** Chẳng hạn ký tự `&` trong nội dung cần viết là `&amp;`:

```xml
<description>Validation &amp; normalization for order data.</description>
```

Viết dấu `&` trần trong nội dung XML sẽ làm tệp không hợp lệ. Tương tự, dấu `<` bên trong văn bản cần là `&lt;`. Không nhúng HTML tùy tiện vào `description`; metadata này nên vẫn có ý nghĩa ở dạng văn bản thuần trên công cụ khác.

Nếu đoạn mô tả dài nhiều dòng trong XML, phần khoảng trắng/xuống dòng có thể ảnh hưởng đến cách công cụ hiển thị. Một hoặc hai câu gọn, tránh thụt đầu dòng không cần thiết bên trong nội dung, thường dễ tái sử dụng nhất.

## 4. `<url>`: trang chủ của dự án, không phải địa chỉ Maven repository

`<url>` ngay bên dưới `<project>` cho biết **trang web hoặc trang tài liệu chính của dự án**:

```xml
<url>https://example.org/projects/order-core</url>
```

Giá trị này nên dẫn tới nơi người dùng có thể đọc giới thiệu, hướng dẫn, bản phát hành hoặc điều hướng sang tài liệu chính thức. Với thư viện mở nguồn, một trang GitHub chứa README rõ ràng cũng có thể là URL dự án nếu đó là nơi duy trì nội dung chính.

Không nhầm `project.url` với các URL có mục đích khác:

| Vị trí trong POM | Ý nghĩa |
| --- | --- |
| `<project><url>...` | Trang giới thiệu hoặc trang chủ dự án. |
| `<scm><url>...` | Trang để xem mã nguồn/version control. |
| `<issueManagement><url>...` | Trang hệ thống quản lý issue/bug. |
| `<ciManagement><url>...` | Trang pipeline hoặc hệ thống tích hợp liên tục. |
| `<organization><url>...` | Trang của tổ chức sở hữu/quản lý dự án. |
| `<licenses><license><url>...` | Văn bản hoặc thông tin giấy phép. |
| `<distributionManagement><repository><url>...` | Điểm đến triển khai artifact khi dùng cơ chế deploy phù hợp. |

Đặt URL của repository quản lý artifact ở `<project><url>` **không cấu hình được nơi Maven tải dependency hoặc nơi `mvn deploy` đẩy artifact lên**. Đó là các cơ chế cấu hình riêng.

Trong liên kết XML có query string, ký tự `&` vẫn phải được escape bằng `&amp;`, ví dụ:

```xml
<url>https://example.org/docs?lang=vi&amp;section=overview</url>
```

Các địa chỉ `example.org` trong bài dùng để minh họa cấu trúc. Khi áp dụng, phải thay bằng URL thật, truy cập được và phù hợp với quyền công khai của dự án.

## 5. Những nhóm metadata mô tả dự án khác

Ngoài ba trường cơ bản, POM có các phần tử chính thức cho tổ chức, giấy phép, người đóng góp, mã nguồn và hệ thống vận hành. Không phải dự án nào cũng cần khai báo toàn bộ, nhưng các trường được sử dụng phải chính xác.

| Phần tử | Mô tả | Khi nào hữu ích? |
| --- | --- | --- |
| `<inceptionYear>` | Năm bắt đầu dự án, thường là bốn chữ số. | Báo cáo, thông tin bản quyền, tài liệu lịch sử. |
| `<organization>` | Tên và website của tổ chức liên quan. | Dự án có tổ chức phụ trách rõ ràng. |
| `<licenses>` | Một hoặc nhiều giấy phép áp dụng cho **dự án này**. | Thư viện được phân phối/chia sẻ cho người khác. |
| `<developers>` | Thành viên trực tiếp phát triển và duy trì. | Công bố người phụ trách hoặc nhóm bảo trì. |
| `<contributors>` | Người đóng góp khác. | Ghi nhận cộng tác viên. |
| `<scm>` | Địa chỉ mã nguồn và cách công cụ truy cập hệ quản lý phiên bản. | Muốn người đọc tìm Git hoặc plugin SCM/release dùng thông tin này. |
| `<issueManagement>` | Hệ thống tiếp nhận, theo dõi vấn đề. | Dự án có issue tracker. |
| `<ciManagement>` | Công cụ hoặc trang CI. | Muốn liên kết tới pipeline build/test. |
| `<mailingLists>` | Các kênh mailing list hỗ trợ dự án. | Dự án cộng đồng dùng mailing list. |

### 5.1. `<organization>`

```xml
<organization>
    <name>Example Engineering</name>
    <url>https://example.org</url>
</organization>
```

Tên tổ chức ở đây là metadata dành cho người đọc; nó không phải `groupId` và không quyết định tên package Java. Tên tổ chức hoặc website có thể thay đổi mà không làm tọa độ artifact tự đổi.

### 5.2. `<licenses>`

```xml
<licenses>
    <license>
        <name>Apache-2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
        <distribution>repo</distribution>
    </license>
</licenses>
```

- `name` nên là tên giấy phép rõ ràng; dùng định danh SPDX phổ biến như `Apache-2.0` khi phù hợp.
- `url` trỏ đến nội dung hoặc trang thông tin của giấy phép.
- `distribution` mô tả phương thức phân phối theo mô hình Maven, thường là `repo` hoặc `manual`.

**Không sao chép khai báo Apache-2.0 chỉ vì ví dụ dùng nó.** Metadata phải phản ánh giấy phép thực sự đã được chủ sở hữu áp dụng cho mã nguồn; khai báo trong POM tự nó không cấp quyền pháp lý cho phần mã được phân phối. Cũng không liệt kê giấy phép của tất cả dependency trong `<licenses>` của dự án: phần này mô tả giấy phép **dự án**, còn việc thống kê giấy phép dependency là một bài toán riêng.

### 5.3. `<developers>` và `<contributors>`

```xml
<developers>
    <developer>
        <id>maintainer</id>
        <name>Example Maintainer</name>
        <email>maintainer@example.org</email>
        <roles>
            <role>maintainer</role>
            <role>developer</role>
        </roles>
    </developer>
</developers>
```

Đối với `developers`, `id` giúp nhận diện người phát triển trong thông tin dự án, `name` là tên hiển thị, `email` là kênh liên hệ công khai nếu có, và `roles` mô tả vai trò. `contributors` dùng cấu trúc tương tự để ghi nhận người đóng góp; không phải ai đóng góp cũng cần thông tin đầy đủ như người duy trì chính.

Đừng đưa email cá nhân không được phép công khai, mật khẩu, token hay dữ liệu nội bộ vào POM sẽ được phát hành công khai. Khi có nhóm quản trị chung, cần thống nhất cách công bố địa chỉ liên hệ.

### 5.4. `<scm>`

```xml
<scm>
    <connection>scm:git:https://git.example.org/team/order-core.git</connection>
    <developerConnection>scm:git:ssh://git@git.example.org/team/order-core.git</developerConnection>
    <url>https://git.example.org/team/order-core</url>
    <tag>HEAD</tag>
</scm>
```

- `connection` là SCM URL mà công cụ có thể dùng để truy cập mã nguồn, thường cho mục đích đọc.
- `developerConnection` mô tả kết nối dành cho người/công cụ có quyền ghi, nếu có.
- `url` là trang người đọc mở trong trình duyệt.
- `tag` biểu thị nhãn hoặc phiên bản nguồn được liên kết; giá trị `HEAD` thường được dùng khi chưa chỉ định tag phát hành cụ thể.

Cú pháp `scm:git:...` tuân theo quy ước Maven SCM; nó khác URL HTTP của dự án. Bản phát hành có thể yêu cầu một tag/commit chính xác theo quy trình release. Thông tin `scm` là metadata, không tự clone repository mỗi khi Maven build.

### 5.5. `<issueManagement>` và `<ciManagement>`

```xml
<issueManagement>
    <system>GitHub Issues</system>
    <url>https://github.com/example/order-core/issues</url>
</issueManagement>

<ciManagement>
    <system>GitHub Actions</system>
    <url>https://github.com/example/order-core/actions</url>
</ciManagement>
```

Hai khối mô tả **nơi theo dõi issue** và **nơi xem CI**. Chỉ thêm những hệ thống dự án thực sự dùng. Ghi một URL pipeline trong POM không đồng nghĩa pipeline đã được cấu hình hoặc chạy thành công; pipeline vẫn do hệ thống CI quản lý.

## 6. Ví dụ `pom.xml` độc lập có metadata hợp lệ

Dưới đây là một POM mẫu **hoàn chỉnh về cấu trúc XML** cho một thư viện Java giả định. Dự án được mô tả theo Maven model 4.0.0, có tọa độ, tên hiển thị, mô tả, URL, tổ chức, giấy phép, người duy trì và mã nguồn. Các URL `example.org` cùng danh tính mô phỏng chỉ phục vụ học tập.

Tệp: `pom.xml` tại gốc dự án.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>order-metadata-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Order Metadata Demo</name>
    <description>Thư viện minh họa metadata dự án Maven.</description>
    <url>https://example.org/projects/order-metadata-demo</url>
    <inceptionYear>2026</inceptionYear>

    <organization>
        <name>Example Engineering</name>
        <url>https://example.org</url>
    </organization>

    <licenses>
        <license>
            <name>Apache-2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>demo-maintainer</id>
            <name>Example Maintainer</name>
            <email>maintainer@example.org</email>
            <roles>
                <role>maintainer</role>
            </roles>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://git.example.org/team/order-metadata-demo.git</connection>
        <developerConnection>scm:git:ssh://git@git.example.org/team/order-metadata-demo.git</developerConnection>
        <url>https://git.example.org/team/order-metadata-demo</url>
        <tag>HEAD</tag>
    </scm>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

POM này có thể được Maven đọc và xử lý khi môi trường có Java/Maven phù hợp và có thể tải plugin nếu chưa cache. Có thể dùng `mvn validate` để kiểm tra quá trình Maven nạp mô hình dự án; `mvn package` sẽ thực thi vòng đời đóng gói. Nếu chưa có mã nguồn ở `src/main/java` thì JAR được tạo sẽ không chứa các lớp ứng dụng; metadata không tự sinh mã Java. Không cần tạo class Java chỉ để kiểm tra các trường mô tả.

Những địa chỉ và danh tính mô phỏng trong ví dụ phải được thay bằng thông tin có thật **trước khi phát hành**. Đặc biệt giấy phép được ghi trong POM phải phản ánh lựa chọn cấp phép thực tế của dự án.

## 7. Maven đọc và hiển thị metadata như thế nào?

Các plugin, hệ thống báo cáo và công cụ phát hành có thể truy cập `project.name`, `project.description`, `project.url` và các thuộc tính tương ứng sau khi Maven dựng mô hình dự án.

### 7.1. Xem một thuộc tính bằng Maven Help Plugin

Trong thư mục chứa POM, chạy:

```bash
mvn help:evaluate -Dexpression=project.name -q -DforceStdout
```

Với POM ở mục 6, kết quả đánh giá của `project.name` là:

```text
Order Metadata Demo
```

Tương tự, có thể kiểm tra:

```bash
mvn help:evaluate -Dexpression=project.description -q -DforceStdout
mvn help:evaluate -Dexpression=project.url -q -DforceStdout
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
```

Ý nghĩa: `-Dexpression=...` chọn một biểu thức của mô hình Maven; `-q` hạn chế log; `-DforceStdout` yêu cầu goal in giá trị ra stdout trong quiet mode. Maven Help Plugin có thể phải tải từ repository khi chưa có trong cache. Cấu hình môi trường, profile, phiên bản plugin và tiến trình chạy có thể phát sinh thông báo khác; giá trị cần đối chiếu là nội dung được đánh giá.

### 7.2. Xem effective POM

```bash
mvn help:effective-pom
```

Lệnh này hiển thị POM sau khi Maven xử lý cấu hình, kế thừa và các mặc định liên quan. Nó hữu ích khi một trường metadata xuất hiện dù bạn không viết trực tiếp trong POM con, hoặc giá trị URL khác với điều mong đợi. Có thể hướng output ra tệp để so sánh, ví dụ:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Tệp `effective-pom.xml` là kết quả kiểm tra, không phải tệp nguồn để tùy tiện thay thế `pom.xml`. Tùy phiên bản plugin và profile đang bật, effective model có thể khác nhau. Nếu chạy với `-f path/to/pom.xml` trong build thật, hãy dùng cùng `-f` khi kiểm tra.

### 7.3. Metadata có thể xuất hiện ở đâu?

- **Tài liệu website Maven:** Maven Site và các reporting plugin có thể dùng thông tin mô tả, tổ chức, người phát triển, giấy phép, SCM để tạo nội dung.
- **Project Info Reports Plugin:** tạo trang thông tin tổng quan, licenses, team, SCM, issue management, CI management và nhiều báo cáo khác nếu được cấu hình/kích hoạt.
- **POM được phân phối cùng artifact:** người dùng kho artifact có thể xem tọa độ và metadata đã khai báo trong POM được công bố.
- **Plugin release hoặc công cụ quản lý mã nguồn:** có thể đọc `scm` và các trường bổ sung để thực thi các quy trình đã được cấu hình.

**Maven không mặc nhiên tạo website, release, issue tracker hoặc CI chỉ vì có metadata.** Để có báo cáo hay triển khai artifact, cần cấu hình và chạy các goal/plugin thích hợp. Ví dụ, `mvn package` thông thường không đồng nghĩa `mvn site` hoặc `mvn deploy`.

## 8. Metadata trong parent POM và dự án nhiều module

Giả sử repository có một POM cha và hai module:

```text
shop/
├── pom.xml                <- parent/aggregator
├── order-api/
│   └── pom.xml
└── order-core/
    └── pom.xml
```

Parent có thể khai báo metadata dùng chung như tổ chức, giấy phép và SCM. Các POM con khai báo `<parent>` để kế thừa. Ví dụ phần liên quan trong parent:

```xml
<groupId>org.example.shop</groupId>
<artifactId>shop-parent</artifactId>
<version>1.0.0</version>
<packaging>pom</packaging>

<organization>
    <name>Example Shop Team</name>
    <url>https://example.org/shop</url>
</organization>

<licenses>
    <license>
        <name>Apache-2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
</licenses>

<modules>
    <module>order-api</module>
    <module>order-core</module>
</modules>
```

Đây là **đoạn minh họa đặt bên trong `<project>` của parent**, không phải tệp POM hoàn chỉnh.

POM con có thể đặt tên và mô tả riêng:

```xml
<parent>
    <groupId>org.example.shop</groupId>
    <artifactId>shop-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>

<artifactId>order-api</artifactId>
<name>Shop Order API</name>
<description>Module cung cấp HTTP API cho chức năng đơn hàng.</description>
<url>https://example.org/shop/order-api</url>
```

Điểm cần nhớ:

1. `<modules>` trong parent POM tạo quan hệ **aggregation** (tham gia reactor); `<parent>` trong POM con tạo quan hệ **inheritance** (kế thừa cấu hình). Hai quan hệ này không đồng nghĩa.
2. Nhiều trường mô tả (ví dụ organization, licenses, scm, developers) có thể được kế thừa theo quy tắc Maven. Giá trị hiệu lực còn phụ thuộc cấu hình và quy tắc nội suy/điều chỉnh của mô hình.
3. `url` hoặc thông tin SCM của module có thể được suy ra/điều chỉnh từ parent theo quy tắc Maven; **không đoán URL cuối chỉ bằng cách nhìn parent**. Xem `help:effective-pom` và đối chiếu liên kết thực tế.
4. Mỗi module vẫn cần `name` và `description` đủ cụ thể để người dùng phân biệt. Không nên dùng cùng một mô tả chung nếu mục đích các module khác nhau.
5. Nếu module có giấy phép khác với parent, phải khai báo metadata phản ánh thực tế; không mặc nhiên xem toàn bộ module cùng một giấy phép khi điều đó không đúng.

Khi thiết kế metadata cho monorepo, có thể chuẩn hóa các trường thực sự dùng chung ở parent, đồng thời để mỗi module tự mô tả công dụng của mình. Cách này giảm lặp và tránh công bố sai trách nhiệm hoặc website.

## 9. Metadata và phát hành artifact

Khi một thư viện được phát hành tới kho Maven, người tải thường có thể truy cập POM tương ứng với artifact. Metadata trong POM giúp người dùng và công cụ tìm hiểu **nguồn gốc, giấy phép, người bảo trì và nơi gửi báo lỗi**.

Tuy nhiên, cần phân biệt các việc sau:

- `<project><url>` giới thiệu dự án; nó **không** xác định kho phát hành.
- `<licenses>` mô tả giấy phép; nó **không** thay thế văn bản cấp phép, quy trình pháp lý hoặc kiểm tra license.
- `<scm>` cho biết mã nguồn; nó **không** chứng minh mã nguồn đó đã được build đúng tag nếu pipeline phát hành không kiểm tra.
- `<developers>` mô tả người duy trì; nó **không** cấp quyền upload artifact.
- `<distributionManagement>` và công cụ/phương thức triển khai tương ứng phục vụ việc publish; repository có thể có thêm yêu cầu xác minh riêng.

Một số kho artifact đặt quy tắc kiểm tra metadata khi công bố thư viện. Quy tắc cụ thể phụ thuộc kho và có thể thay đổi, vì vậy hãy kiểm tra chính sách hiện hành của kho định phát hành. Dự án ứng dụng nội bộ có thể chọn mức metadata phù hợp, nhưng vẫn nên có ít nhất tên, mô tả và một liên kết tài liệu đáng tin.

Đối với thư viện dùng chung, thiếu `name` hoặc `description` làm trải nghiệm khám phá khó hơn ngay cả khi dependency vẫn giải quyết bình thường; thông tin URL lỗi hoặc license không chính xác có thể gây nhầm lẫn khi người dùng đánh giá tính phù hợp của thư viện.

## 10. Nguyên tắc viết metadata chất lượng

**Tên hiển thị (`name`):** dùng tên phản ánh module, có thể đọc thành câu; tránh tên kỹ thuật vô nghĩa với người sử dụng. Ví dụ `<name>Order Validation Core</name>` rõ hơn `<name>backend-lib-2</name>`.

**Mô tả (`description`):** một hoặc hai câu nêu chức năng chính, không quảng cáo quá mức. Ví dụ “Kiểm tra và chuẩn hóa dữ liệu đơn hàng trước khi ghi xuống cơ sở dữ liệu” tốt hơn “Framework tốt nhất cho mọi dự án”.

**URL (`url`):** dẫn đến tài nguyên dự án có người duy trì, không nên dùng liên kết trang cá nhân không liên quan hoặc đường dẫn nội bộ khi POM phát hành công khai.

**Tổ chức, người duy trì và giấy phép:** chỉ cung cấp thông tin được phép công bố; dùng tên và giấy phép chính xác. Nếu một kho yêu cầu metadata nhất định, bổ sung theo chính sách đó.

**Thông tin vận hành (`scm`, `issueManagement`, `ciManagement`):** tách rõ ba vai trò. Một đường dẫn repository Git không thay thế trang issue tracker hoặc thông tin CI.

**Tính nhất quán:** đồng bộ metadata với README, repository, release và POM cha. Sau khi đổi tên repo, chuyển hệ thống issue hoặc đổi website, cần cập nhật POM vì một liên kết cũ có thể được phát hành tới nhiều người dùng.

## 11. Lỗi thường gặp

### Lỗi 1: Nhầm `name` với `artifactId`

Thay `<name>` rồi kỳ vọng người dùng sẽ đổi dependency coordinates. Tên kỹ thuật vẫn lấy từ `groupId:artifactId:version`. Muốn đổi artifact cần xem xét ảnh hưởng tới người sử dụng và quy trình phát hành.

### Lỗi 2: Coi `description` như nơi chứa README

Đưa hàng trang hướng dẫn, HTML dài hoặc ghi chú build vào `description`. Metadata này nên ngắn, đọc được ở dạng text; nội dung học tập, API và hướng dẫn chi tiết đặt trong README/docs.

### Lỗi 3: Viết XML không hợp lệ

Ví dụ sai:

```xml
<description>Fast & simple</description>
```

Ví dụ hợp lệ:

```xml
<description>Fast &amp; simple</description>
```

Ký tự `&` cần được mã hóa. Dùng editor hỗ trợ XML và chạy `mvn validate` để phát hiện lỗi cú pháp POM.

### Lỗi 4: Đặt URL sai mục đích

Nhập URL Maven repository vào `<project><url>` rồi mong Maven tải dependency từ đó. Muốn cấu hình tải dependency phải dùng cơ chế repository/mirror phù hợp; muốn cấu hình nơi deploy artifact phải dùng cấu hình publish phù hợp.

### Lỗi 5: Ghi giấy phép không đúng với mã nguồn

Sao chép `Apache-2.0` từ ví dụ nhưng dự án chưa được cấp phép theo Apache License. Chỉ công bố giấy phép thực sự áp dụng cho dự án và xác minh với chủ sở hữu khi cần.

### Lỗi 6: Metadata parent áp dụng sai cho mọi module

Tất cả module kế thừa một mô tả hoặc URL chung nhưng mỗi module có mục đích và trang riêng. Cần kiểm tra effective POM và ghi metadata đặc thù ở POM con.

### Lỗi 7: Lưu bí mật trong metadata

Ghi token truy cập trong `scm`, `url`, `developers` hoặc giá trị công khai khác. POM có thể được chia sẻ và xuất bản cùng artifact; secret nên do CI hoặc môi trường bảo mật quản lý.

### Lỗi 8: Tin rằng metadata kích hoạt tích hợp tự động

Khai báo `<ciManagement>` không tạo pipeline, `<issueManagement>` không tạo hệ thống issue và `<scm>` không tự thực hiện release. Những tích hợp đó cần công cụ và cấu hình riêng.

## 12. Tự kiểm tra hiểu bài

**Câu 1.** Đổi `<name>Order Domain</name>` thành `<name>Order Core</name>` trong POM nhưng giữ nguyên `groupId`, `artifactId`, `version`. Dependency của người dùng có đổi tọa độ không?

**Đáp án:** Không. `name` thay đổi tên hiển thị, còn tọa độ được xác định bởi các trường kỹ thuật.

**Câu 2.** Một người muốn đặt link trang chứa mã nguồn Git ở đâu, và muốn đặt link trang giới thiệu dự án ở đâu?

**Đáp án:** Dùng `<scm><url>...` cho mã nguồn và `<project><url>...` cho trang chủ/tài liệu dự án. Hai URL có thể cùng trỏ đến trang repo nếu đó thật sự là nơi giới thiệu chính, nhưng vai trò của hai phần tử khác nhau.

**Câu 3.** `<licenses>` trong POM nên chứa giấy phép của chính module hay tất cả thư viện phụ thuộc?

**Đáp án:** Chủ yếu mô tả giấy phép áp dụng cho chính dự án. Tổng hợp giấy phép dependencies là vấn đề kiểm tra dependency riêng.

**Câu 4.** Một POM con không có `<organization>` nhưng effective POM vẫn hiển thị organization. Điều gì có thể giải thích hiện tượng này?

**Đáp án:** POM con có thể kế thừa metadata từ parent. Dùng `mvn help:effective-pom` để xác định giá trị đang có hiệu lực và kiểm tra chuỗi kế thừa.

**Câu 5.** Một repository công khai yêu cầu website dự án và địa chỉ SCM hợp lệ, nhưng POM chứa `https://example.org/...` từ bản học tập. Cần làm gì?

**Đáp án:** Thay bằng website/mã nguồn thực, kiểm tra quyền truy cập của người đọc, và xác minh các trường liên quan trước khi publish. Không xem URL minh họa là dữ liệu phát hành.

## Tài liệu tham khảo

- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): các phần tử `name`, `description`, `url`, `organization`, `licenses`, `developers`, `scm`, `issueManagement` và những nhóm metadata khác.
- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): mô hình POM, parent, inheritance và effective POM.
- [Apache Maven – POM Code Conventions](https://maven.apache.org/developers/conventions/code.html): thứ tự phần tử khuyến nghị khi tổ chức `pom.xml`.
- [Apache Maven – SCM URLs](https://maven.apache.org/pom-scm-urls.html): cú pháp `scm:git:...` và các loại SCM connection.
- [Apache Maven – Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/): những báo cáo dựa trên metadata của dự án.
- [Apache Maven – Help Plugin: evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html) và [effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): cách xem giá trị metadata sau khi Maven xử lý.
