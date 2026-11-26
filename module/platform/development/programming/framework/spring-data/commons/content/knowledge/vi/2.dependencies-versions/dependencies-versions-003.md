# Chọn Java, Spring Framework, Commons và store module tương thích

Một ứng dụng Spring Data không chạy trên một dependency duy nhất. Nó chạy trên một tập hợp gồm Java, Spring Framework, Spring Data Commons, module tích hợp kho dữ liệu, thư viện truy cập dữ liệu và hệ quản trị phía ngoài. Khi các thành phần này không cùng đáp ứng yêu cầu tương thích, ứng dụng có thể biên dịch thành công nhưng lỗi ngay lúc khởi tạo repository hoặc chỉ lỗi khi thực hiện một truy vấn cụ thể.

Trong chương **Phụ thuộc và phiên bản**, bài học này trình bày cách chọn một bộ dependency có căn cứ, quản lý phiên bản tập trung và kiểm tra bộ thực sự được sử dụng. Phạm vi là Spring Data Commons cùng các store module sử dụng những abstraction như Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing.

Các ví dụ cấu hình dùng biến phiên bản để minh họa cơ chế quản lý. Khi áp dụng vào dự án, hãy gán giá trị cụ thể theo tài liệu yêu cầu hệ thống, dependency được quản lý và ghi chú phát hành của bộ phiên bản đã chọn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định các tầng phiên bản cần tương thích thay vì chỉ nhìn vào `spring-data-commons`.
- Chọn điểm xuất phát phù hợp cho ứng dụng dùng Spring Boot hoặc tự quản lý Spring Framework.
- Giải thích vai trò của release train và BOM trong việc đồng bộ Spring Data Commons với store module.
- Phân biệt JDK dùng để build, Java target của ứng dụng và JVM dùng để chạy.
- Đọc dependency graph để nhận ra override, dependency bắc cầu và khác biệt giữa compile classpath với runtime classpath.
- Lập quy trình nâng cấp và kiểm tra theo những tính năng dữ liệu thực sự được sử dụng.

## 2. Bức tranh dependency: cần chọn cả một bộ

Xét ứng dụng lưu khách hàng bằng JPA. Repository của ứng dụng có thể dùng `CrudRepository`, `Pageable`, projection và các trường auditing. Các API đó liên quan đến Commons, nhưng hành vi chạy còn cần Spring Data JPA, Spring Framework, JPA provider, JDBC driver và hệ quản trị cơ sở dữ liệu.

Một ứng dụng MongoDB có thể vẫn dùng nhiều kiểu của Commons, nhưng tầng truy cập dữ liệu phía dưới là Spring Data MongoDB và MongoDB driver. Chọn đúng Commons mà chọn sai module hoặc driver vẫn có thể làm ứng dụng không khởi động được.

```text
Mã ứng dụng
    |
    +-- Spring Boot, nếu sử dụng
    |       +-- dependency management cho bộ thành phần
    |
    +-- Spring Framework
    |       +-- container, chuyển đổi kiểu, giao dịch và hạ tầng liên quan
    |
    +-- Spring Data store module
    |       +-- Spring Data Commons
    |       +-- thư viện truy cập dữ liệu / provider / driver
    |
    +-- JVM dùng để chạy
            +-- kết nối tới phiên bản hệ quản trị được hỗ trợ
```

Sơ đồ thể hiện các tầng cần xem xét, không thay thế dependency graph thực tế của một dự án.

| Thành phần | Cần xác định điều gì? | Sai lệch thường gây ra gì? |
| --- | --- | --- |
| Java | JDK build, mức bytecode, Java API được phép dùng và JVM runtime | Lỗi bytecode hoặc dùng API không có ở runtime |
| Spring Framework | Dòng phiên bản mà bộ Spring Data yêu cầu | Thiếu lớp, thiếu phương thức hoặc lỗi khởi tạo hạ tầng |
| Spring Data Commons | Phiên bản được chọn cùng store module | Module gọi API Commons không tồn tại trong JAR được nạp |
| Store module | Loại store và phiên bản trong bộ phát hành phù hợp | Repository, mapping hoặc truy vấn không hoạt động đúng |
| Provider hoặc driver | Phiên bản phù hợp với module và môi trường lưu trữ | Lỗi giao thức, mapping, kết nối hoặc hành vi không được hỗ trợ |
| Hệ quản trị | Phiên bản, topology và tính năng cần sử dụng | Tính năng module cung cấp không thực thi được trên môi trường thật |
| Công cụ build và plugin | Khả năng chạy với JDK, cấu hình compiler, đóng gói và kiểm thử | Build hoặc đóng gói khác với cấu hình mong đợi |

Có bốn ý nghĩa của “tương thích” cần tách biệt: tương thích mã nguồn, tương thích nhị phân, đáp ứng môi trường chạy và đáp ứng hành vi nghiệp vụ. Biên dịch thành công mới chỉ cung cấp một phần bằng chứng.

## 3. Release train và BOM giải quyết bài toán nào?

### 3.1. Release train là bộ phát hành phối hợp

Các module Spring Data được phát hành theo những bộ phối hợp, thường được gọi là **release train**. Mục đích là cung cấp một tập phiên bản module có quan hệ tương thích được xác định trong phạm vi bộ phát hành đó.

Tên hoặc số phiên bản release train không nhất thiết là số phiên bản của từng artifact. Vì vậy, không lấy phiên bản của BOM rồi chép nguyên vào `spring-data-commons`, `spring-data-jpa` hoặc mọi store module.

Cũng không suy luận rằng hai artifact tương thích chỉ vì trông giống nhau ở số major hoặc minor. Quan hệ tương thích phải xuất phát từ bộ dependency được quản lý và yêu cầu của module.

### 3.2. BOM quản lý phiên bản, không thêm mọi dependency

**BOM**, viết tắt của Bill of Materials, mô tả phiên bản được quản lý cho một tập dependency. Trong Maven, BOM thường được import ở `dependencyManagement`. Trong Gradle, có thể sử dụng cơ chế platform để đưa các ràng buộc phiên bản vào quá trình phân giải.

Cần phân biệt hai thao tác:

- **Quản lý phiên bản:** xác định phiên bản sẽ được chọn khi dependency liên quan tham gia dependency graph.
- **Khai báo dependency:** đưa thư viện mà dự án cần vào cấu hình phụ thuộc tương ứng.

Import một BOM không có nghĩa là tải toàn bộ module Spring Data vào ứng dụng. Nó cũng không tự cấu hình kết nối cơ sở dữ liệu, tạo repository, chọn JDK hoặc chạy migration dữ liệu.

### 3.3. Chọn một nguồn điều phối chính

Hai lộ trình thường gặp là:

| Bối cảnh | Điểm xuất phát | Vai trò quản lý phiên bản |
| --- | --- | --- |
| Ứng dụng dùng Spring Boot | Một phiên bản Spring Boot phù hợp yêu cầu dự án | Dùng dependency management của Boot làm bộ mặc định, bao gồm các phiên bản Spring và Spring Data được quản lý |
| Ứng dụng tự quản lý Spring Framework | Bộ Spring Data và dòng Spring Framework tương thích theo yêu cầu công bố | Quản lý rõ BOM Spring Data, Spring Framework và các thành phần ngoài phạm vi BOM |

Hai lộ trình này đều yêu cầu kiểm tra Java, driver và hệ quản trị. Điểm khác biệt là nơi chịu trách nhiệm điều phối bộ thư viện.

Nếu ứng dụng đang dùng bộ do Boot quản lý, việc thêm một BOM Spring Data khác hoặc đặt phiên bản riêng cho Commons là một thay đổi có ảnh hưởng tới bộ đó. Cần biết chính xác dependency nào sẽ bị thay đổi trước khi coi cấu hình mới là phù hợp.

## 4. Lộ trình dùng Spring Boot

### 4.1. Bắt đầu từ yêu cầu của ứng dụng và môi trường

Trước khi chọn một phiên bản Boot, cần trả lời:

1. Môi trường triển khai cho phép dùng dòng Java nào?
2. Dự án cần tính năng nào của Spring Data hoặc store module?
3. Hệ quản trị và driver hiện có thuộc phạm vi hỗ trợ nào?
4. Chính sách bảo trì của dự án yêu cầu dòng phát hành còn được hỗ trợ như thế nào?
5. Các thư viện tích hợp khác có giới hạn Spring Framework hoặc Java hay không?

Đối chiếu các câu trả lời với yêu cầu hệ thống và danh sách dependency được quản lý của phiên bản Boot dự kiến. Không chỉ chọn một starter rồi giả định phần còn lại tự phù hợp với hạ tầng hiện có.

### 4.2. Để dependency management chọn Commons và store module

Ví dụ dưới đây là phần cấu hình Maven minh họa cách import BOM của Boot. Property `boot.version` phải được định nghĩa bằng giá trị đã chọn cho dự án.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${boot.version}</version>
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
```

Starter JPA đưa vào các dependency cần thiết cho hướng tích hợp JPA theo bộ Boot quản lý. Ứng dụng vẫn cần cấu hình datasource và driver phù hợp với cơ sở dữ liệu sử dụng.

Trong cách khai báo này, không đặt một version tùy ý lên starter, `spring-data-jpa` hoặc `spring-data-commons`. Store module đưa Commons vào dependency graph theo quan hệ bắc cầu; dependency management quyết định phiên bản thực tế.

Nếu ứng dụng chủ động khai báo Commons vì trực tiếp sử dụng API của thư viện, hãy tiếp tục để cùng nguồn dependency management quản lý phiên bản đó. Việc có thêm một khai báo trực tiếp không phải lý do để chọn một phiên bản Commons độc lập.

### 4.3. Phân biệt parent của Boot với import BOM

Một dự án Maven có thể dùng parent của Boot hoặc import BOM khi cần giữ parent khác. Hai cách này không cung cấp hoàn toàn cùng một phạm vi cấu hình.

BOM tập trung vào dependency management. Parent có thể cung cấp thêm cấu hình build và plugin theo thiết kế của nó. Vì vậy, khi chỉ import BOM, cần cấu hình compiler, plugin build và các giá trị liên quan một cách rõ ràng; không mặc định chúng đã giống một dự án dùng parent.

Ví dụ, đặt một property có tên `java.version` chỉ có tác dụng khi cấu hình hoặc plugin liên quan thực sự sử dụng property đó. Tên property không tự điều khiển mọi công cụ trong chuỗi build.

### 4.4. Ví dụ tương ứng với Gradle

Một đoạn Gradle Kotlin DSL có thể thể hiện lựa chọn BOM bằng platform:

```kotlin
val bootVersion: String by project

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:$bootVersion")
    )
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
```

Đây là một phần của build script, với `bootVersion` được cấu hình ở dự án. Cấu hình plugin, toolchain và đóng gói ứng dụng phải được xác định riêng theo cách tổ chức build.

Cơ chế platform tham gia phân giải phiên bản của Gradle. Vẫn cần xem phiên bản đã resolve khi có dependency, constraint hoặc rule khác cùng tác động. Không coi việc nhìn thấy dòng import BOM là đủ để kết luận mọi version cuối cùng đều đúng như dự kiến.

## 5. Lộ trình không dùng Spring Boot

### 5.1. Chọn bộ Spring Data trước khi ghép dependency

Khi tự quản lý Spring Framework, cần xác định:

- Bộ phát hành Spring Data chứa store module cần dùng.
- Dòng Spring Framework phù hợp với bộ Spring Data đó.
- Mức Java tối thiểu và phạm vi runtime được hỗ trợ của các thành phần.
- Provider, driver và các thư viện bổ sung ngoài phạm vi quản lý hiện có.

Có thể sử dụng `spring-data-bom` để đồng bộ các module Spring Data. Nếu quản lý Framework bằng `spring-framework-bom`, phải chọn phiên bản Framework phù hợp với yêu cầu của bộ Spring Data, thay vì ghép hai BOM bất kỳ.

Ví dụ Maven sau thể hiện vị trí quản lý phiên bản. Các property là đầu vào phải được xác định trước theo quan hệ tương thích.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${framework.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>${data.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jpa</artifactId>
    </dependency>
</dependencies>
```

Đoạn cấu hình này không phải một ứng dụng JPA hoàn chỉnh. Còn cần các thành phần và cấu hình như provider, datasource, transaction manager và kích hoạt repository phù hợp. Các dependency ngoài phạm vi được BOM quản lý phải có nguồn quản lý phiên bản rõ ràng.

### 5.2. Thư viện dùng Commons khác với ứng dụng dùng store

Một thư viện tiện ích chỉ cung cấp API dựa trên `Page`, `Sort` hoặc các abstraction chung có thể cần dependency trực tiếp vào `spring-data-commons` mà không cần chọn một store module.

Ngược lại, một ứng dụng muốn có repository lưu dữ liệu cần module tích hợp tương ứng. Chỉ thêm Commons không tự tạo implementation cho một kho dữ liệu cụ thể.

| Nhu cầu | Dependency cần cân nhắc |
| --- | --- |
| Thư viện dùng các kiểu dùng chung của Spring Data | Commons, với phạm vi dependency phù hợp cách thư viện công bố API |
| Ứng dụng truy cập cơ sở dữ liệu qua JPA | Module hoặc starter JPA, provider, driver và hạ tầng cần thiết |
| Ứng dụng làm việc với MongoDB | Module hoặc starter MongoDB và driver phù hợp |
| Ứng dụng sử dụng nhiều store | Các module tương ứng trong bộ phiên bản tương thích, cộng cấu hình repository rõ ràng |

Với thư viện tái sử dụng, còn cần chú ý dependency được đưa tới ứng dụng tiêu thụ như thế nào. Nếu public API trả về một kiểu của Commons, ứng dụng tiêu thụ phải có phiên bản phù hợp để biên dịch và chạy API đó. Một version dùng trong quá trình phát triển thư viện không tự bảo đảm mọi ứng dụng tiêu thụ sẽ resolve cùng version.

## 6. Chọn Java: có nhiều phiên bản cần kiểm soát

Một máy có thể cài nhiều JDK. IDE, terminal, build daemon, CI và container có thể sử dụng các bản khác nhau. Do đó, câu “dự án dùng Java nào?” cần được trả lời ở nhiều vị trí.

| Khái niệm | Ý nghĩa | Cần kiểm tra |
| --- | --- | --- |
| JDK chạy công cụ build | Java thực thi Maven, Gradle và các plugin | Công cụ và plugin có chạy được trên JDK này không? |
| Compiler hoặc toolchain | Bộ biên dịch được dùng để tạo class của ứng dụng | Có đúng JDK dự kiến và cấu hình nhất quán trên CI không? |
| Mức Java target | Bytecode và Java API được cho phép với mã ứng dụng | Mã sinh ra có phù hợp runtime mục tiêu không? |
| JVM runtime | Java thật sự chạy ứng dụng đã đóng gói | Có đáp ứng yêu cầu của ứng dụng và toàn bộ dependency không? |

### 6.1. Mức tối thiểu cần đáp ứng toàn bộ dependency

Nếu một dependency yêu cầu JVM mới hơn runtime triển khai, việc hạ Java target của mã ứng dụng không làm dependency đó chạy được trên JVM cũ. JAR của thư viện đã chứa bytecode được biên dịch sẵn.

Tương tự, cấu hình compiler chỉ kiểm soát phần mã mà cấu hình đó tác động. Nó không tự chuyển đổi mọi class của Spring Framework, Commons, store module hoặc driver sang một mức bytecode thấp hơn.

### 6.2. `--release` không thay thế ma trận hỗ trợ

Khi dùng compiler Java hỗ trợ tùy chọn `--release`, tùy chọn này giúp kiểm soát mức ngôn ngữ, bytecode và Java API mục tiêu cho mã được biên dịch. Tuy nhiên, nó không xác nhận mọi dependency tương thích với runtime đã chọn.

Cần kiểm tra riêng yêu cầu Java của bộ Spring và thư viện ngoài. Cũng cần phân biệt “đáp ứng mức Java tối thiểu” với “được thành phần đó công bố hỗ trợ trên một bản Java cụ thể”.

### 6.3. Ghi rõ lựa chọn trong môi trường build và triển khai

Một quyết định Java có thể được ghi dưới dạng:

```text
JDK chạy build: giá trị cụ thể của dự án
Toolchain biên dịch: giá trị cụ thể của dự án
Java release của mã ứng dụng: giá trị cụ thể của dự án
JVM của image hoặc máy triển khai: giá trị cụ thể của dự án
Căn cứ hỗ trợ: yêu cầu của bộ Spring và các dependency liên quan
```

Bản ghi này giúp phát hiện tình huống IDE biên dịch được nhưng container chạy bằng JVM khác. Tùy dự án, toolchain, wrapper và image build là những nơi phù hợp để làm lựa chọn có thể tái lập.

## 7. Chọn store module cùng với provider, driver và server

### 7.1. Commons không thay thế module tích hợp

Commons cung cấp các abstraction dùng chung. Store module diễn giải repository, mapping và truy vấn theo công nghệ cụ thể.

Vì vậy, khi chọn store module, phải kiểm tra cả những khả năng ứng dụng thực sự cần:

- Derived query và các toán tử đang sử dụng.
- `Page`, `Slice`, `Pageable` và `Sort` ở các phương thức liên quan.
- Projection, DTO và cách ánh xạ kết quả.
- Query by Example nếu có.
- Auditing và nguồn thông tin chủ thể.
- Giao dịch, optimistic locking hoặc thao tác cập nhật đặc thù.

Một API xuất hiện trong Commons không chứng minh module và phiên bản bất kỳ đều triển khai mọi khả năng của API đó. Việc chọn đúng phiên bản là điều kiện cần; kiểm tra khả năng hỗ trợ theo store vẫn là một bước riêng.

### 7.2. Đừng dừng ở quan hệ Commons–store module

Với JPA, cần xem thêm provider, JDBC driver và cơ sở dữ liệu. Với MongoDB, cần xem driver và server. Những store khác có chuỗi thành phần tương ứng.

Ngoài số phiên bản, topology cũng có thể ảnh hưởng khả năng sử dụng tính năng. Ví dụ, yêu cầu giao dịch hoặc cách đọc sau ghi có thể cần cấu hình triển khai phù hợp. Một bộ JAR tương thích không tự cấu hình những đặc điểm vận hành này.

Nếu chọn reactive repository, cần module và driver có khả năng reactive phù hợp. Việc thêm các kiểu reactive vào chữ ký phương thức không tự biến một driver đồng bộ thành driver non-blocking.

### 7.3. Nhiều store cần cả đồng bộ phiên bản lẫn cấu hình

Ứng dụng dùng nhiều module nên giữ các module Spring Data trong một bộ được quản lý phù hợp. Đồng thời cần xác định repository nào thuộc module nào, phạm vi quét và mapping tương ứng.

Khi có nhiều repository factory trên classpath, một interface chỉ dựa vào abstraction chung có thể cần thêm thông tin để được gắn với module đúng. Nếu lỗi liên quan nhận diện repository, phải xem cả cấu hình và metadata; không kết luận ngay rằng Commons sai phiên bản.

## 8. Dependency đã khai báo khác dependency được resolve

### 8.1. Dependency bắc cầu tạo ra nhiều đường đi

Một dependency trực tiếp có thể kéo theo các dependency khác. Cùng một artifact có thể được yêu cầu từ nhiều nhánh với các version khác nhau.

```text
Ứng dụng
    +-- store module được quản lý --> Commons thuộc bộ được chọn
    |
    +-- thư viện tích hợp cũ ------> yêu cầu Commons thuộc bộ khác
```

Công cụ build sẽ áp dụng quy tắc phân giải, dependency management và các constraint liên quan để chọn dependency thực tế. Cơ chế cụ thể giữa Maven và Gradle có khác biệt; cần đọc kết quả resolve thay vì suy luận chỉ từ vị trí các dòng khai báo.

### 8.2. Những nguồn có thể làm lệch bộ dependency

| Nguồn tác động | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Version trực tiếp | Đặt riêng version cho Commons bên cạnh starter do Boot quản lý | Xác định lý do override và đối chiếu bộ tương thích |
| Dependency management khác | Parent hoặc BOM khác quản lý trùng artifact | Xem cấu hình có hiệu lực và nguồn quyết định version |
| Dependency bắc cầu | Thư viện cũ yêu cầu một dòng Spring khác | Tìm nhánh đưa vào, nâng cấp hoặc thay tích hợp phù hợp |
| Rule của công cụ build | Constraint, resolution rule hoặc force chọn version khác | Đọc rule và kết quả resolve của configuration liên quan |
| Exclusion | Loại bỏ dependency cần thiết lúc chạy | Kiểm tra lý do loại bỏ và dependency thay thế |
| Môi trường đóng gói | Một số thư viện có ở compile nhưng không có trong gói runtime | Kiểm tra scope, configuration và artifact triển khai |

Không dùng exclusion chỉ để dependency tree trông gọn hơn. Exclusion có thể loại bỏ thư viện mà module vẫn cần lúc thực thi.

### 8.3. Compile classpath và runtime classpath phải được xem riêng

Ứng dụng có thể biên dịch với một phương thức tồn tại ở một phiên bản Commons, rồi chạy với JAR Commons khác không có phương thức đó. Khi ấy lỗi có thể là `NoSuchMethodError`, dù IDE không báo lỗi mã nguồn.

Tương tự, dependency chỉ có trong phạm vi test không chứng minh ứng dụng đóng gói sẽ có dependency đó. Cần xem configuration hoặc scope tương ứng với cách chạy và đóng gói thực tế.

## 9. Đọc dependency graph với một mục tiêu cụ thể

Với Maven Wrapper trên Windows, các lệnh minh họa sau có thể dùng khi kiểm tra một dự án Maven:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.data:*"
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework:*"
.\mvnw.cmd help:effective-pom
```

Hai lệnh đầu giúp tập trung vào các nhánh Spring Data và Spring Framework. Effective POM giúp xem cấu hình sau khi tổng hợp parent, property và dependency management. Tùy vấn đề, cần xem thêm thông tin phân giải chi tiết, dependency runtime và provider hoặc driver liên quan.

Với Gradle, báo cáo dependencies và dependency insight cho configuration phù hợp giúp trả lời những câu hỏi tương tự: artifact nào được chọn, vì sao được chọn và nhánh nào yêu cầu nó.

Khi đọc báo cáo, cần trả lời lần lượt:

1. Commons thực tế có group, artifact và version nào?
2. Các store module đang dùng thuộc bộ nào?
3. Spring Framework có bị trộn nhiều phiên bản ngoài dự kiến không?
4. Version được chọn đến từ BOM, khai báo trực tiếp hay rule khác?
5. Provider và driver runtime là những phiên bản nào?
6. Artifact triển khai có chứa đúng tập dependency dự kiến không?

Đừng chỉ tìm xem artifact “có xuất hiện” hay không. Một dòng bị bỏ qua do xung đột và một dòng được chọn cuối cùng mang ý nghĩa khác nhau. Báo cáo phân giải cần được đọc theo ký hiệu của công cụ đang sử dụng.

## 10. Quy trình chọn bộ phiên bản cho một dự án

### Bước 1: Ghi các ràng buộc trước khi chọn version

Lập bảng nhỏ cho Java triển khai, loại store, phiên bản server, mô hình imperative hoặc reactive, tính năng truy vấn và chính sách bảo trì. Nếu dự án đã có nền tảng Spring Boot, ghi rõ nền tảng đó để tránh vô tình tạo nguồn quản lý thứ hai.

### Bước 2: Chọn nguồn điều phối chính

- Với Boot: chọn phiên bản Boot theo yêu cầu hệ thống và bộ dependency được quản lý.
- Không dùng Boot: chọn bộ Spring Data, xác định Spring Framework phù hợp và quản lý các thành phần liên quan.

Ghi lại căn cứ của lựa chọn, chẳng hạn trang yêu cầu hệ thống và ghi chú phát hành của đúng bộ. Một bảng không ghi rõ phiên bản áp dụng có thể bị hiểu nhầm khi dự án nâng cấp sau này.

### Bước 3: Chọn Java đáp ứng toàn bộ bộ thư viện

Xác định JDK build, toolchain, Java target và JVM triển khai. Kiểm tra cả yêu cầu của công cụ build, plugin và thư viện ngoài Spring.

### Bước 4: Khai báo module cần thiết

Thêm starter hoặc store module đúng nhu cầu. Để nguồn dependency management đã chọn điều phối các version thuộc phạm vi của nó. Các dependency ngoài phạm vi quản lý phải có quyết định phiên bản riêng và căn cứ tương thích rõ ràng.

### Bước 5: Đọc tập dependency đã resolve

Xác nhận Commons, store module, Framework, provider và driver đúng dự kiến. Điều tra các override hoặc xung đột trước khi chuyển sang kiểm tra hành vi.

### Bước 6: Kiểm tra đường chạy dữ liệu thực tế

Khởi động application context và kiểm tra những tính năng ứng dụng sử dụng trên store phù hợp. Kết quả này bổ sung bằng chứng về cấu hình và hành vi, thay vì chỉ xác nhận mã Java biên dịch được.

### Bước 7: Làm cấu hình có thể tái lập

Ghi version cụ thể ở nguồn quản lý đã chọn, thống nhất wrapper, toolchain và môi trường triển khai. Tránh dải phiên bản hoặc lựa chọn thay đổi theo thời điểm nếu dự án cần build có thể tái lập.

## 11. Nâng cấp: thay đổi có kiểm soát thay vì nâng từng JAR tùy ý

### 11.1. Nâng theo nguồn điều phối

Với ứng dụng được Boot quản lý, nâng cấp Boot thường là điểm xuất phát để nhận một bộ Spring và Spring Data được điều phối cùng nhau. Với dự án tự quản lý, cập nhật bộ Spring Data rồi đối chiếu yêu cầu Framework và Java tương ứng.

Một bản sửa lỗi của riêng Commons có thể là nhu cầu thực tế, nhưng override vẫn cần được đánh giá theo phạm vi hỗ trợ và tác động tới module đang dùng. Không mặc định “chỉ tăng patch” là bằng chứng đủ cho mọi tổ hợp.

Nếu buộc phải override, hãy ghi rõ lý do, artifact bị thay đổi, tác động dự kiến và điều kiện để bỏ override. Điều đó giúp lần nâng cấp sau không giữ lại một thay đổi đã hết cần thiết.

### 11.2. Phân biệt thay đổi phiên bản với chuyển đổi thế hệ nền tảng

Một số lần nâng cấp có thể đi qua thay đổi lớn về namespace, API hoặc yêu cầu Java. Chẳng hạn, khi thành phần của dự án chuyển từ API `javax.persistence` sang `jakarta.persistence`, cần đồng bộ entity, provider và thư viện tích hợp theo dòng tương ứng.

Hai namespace này là những tên kiểu khác nhau; cùng xuất hiện trong classpath không tự làm chúng tương đương. Việc đổi một import cũng chưa chứng minh provider và module phía dưới đã phù hợp.

Các thay đổi về quan hệ kế thừa của interface, phương thức deprecated hoặc hành vi truy vấn cũng cần được đọc trong ghi chú nâng cấp của đúng dòng phiên bản.

### 11.3. Kiểm tra theo rủi ro ứng dụng

| Phạm vi kiểm tra | Ví dụ bằng chứng cần có |
| --- | --- |
| Khởi tạo hạ tầng | Context tạo được repository, mapping và converter cần thiết |
| CRUD | Lưu mới, đọc theo ID, cập nhật và xóa chạy trên store mục tiêu |
| Truy vấn | Derived query và truy vấn khai báo được tạo, thực thi đúng điều kiện |
| Phân trang, sắp xếp | Nội dung trang, tổng số nếu cần và thứ tự phù hợp hợp đồng API |
| Projection, Example | Mapping kết quả và quy tắc so khớp vẫn đáp ứng tính năng |
| Auditing | Thông tin thời gian, chủ thể được điền trên các đường ghi liên quan |
| Giao dịch, cạnh tranh | Rollback hoặc phát hiện cập nhật xung đột đúng yêu cầu nếu ứng dụng dùng |
| Đóng gói, triển khai | Gói ứng dụng chạy được bằng JVM và cấu hình thực tế |

Không cần kiểm tra mọi tính năng của toàn bộ hệ sinh thái Spring Data. Chọn những đường chạy ứng dụng đang phụ thuộc và những thay đổi mà ghi chú phát hành chỉ ra có liên quan. Unit test dùng mock repository không xác nhận được mapping, sự tương thích nhị phân hoặc hành vi của driver trên store thật.

## 12. Nhận diện lỗi để tìm đúng tầng

Thông báo lỗi là điểm bắt đầu điều tra, không phải kết luận duy nhất về nguyên nhân.

| Triệu chứng | Nhóm nguyên nhân cần xem | Bằng chứng nên tìm |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Bytecode của một lớp mới hơn khả năng JVM runtime | Lớp gây lỗi, JVM đang chạy và yêu cầu Java của artifact chứa lớp |
| `NoSuchMethodError` | Mã gọi và thư viện runtime không thống nhất về phương thức | JAR chứa lớp, version đã resolve và version được đóng gói |
| `AbstractMethodError` | Implementation không đáp ứng hợp đồng nhị phân đang được dùng | Các API và implementation có bị trộn dòng phiên bản không |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu lớp runtime, sai scope/exclusion hoặc vấn đề khởi tạo lớp | Toàn bộ chuỗi nguyên nhân và dependency runtime liên quan |
| Không tạo được repository | Mapping, package scan, derived query hoặc cấu hình module có vấn đề | Nguyên nhân sâu nhất khi khởi tạo repository và metadata miền |
| Lỗi kết nối hoặc thao tác không được hỗ trợ | Driver, server, topology hoặc cấu hình tính năng | Phiên bản client/server, cấu hình kết nối và yêu cầu của thao tác |

Ví dụ, thấy lỗi khởi tạo repository không có nghĩa phải đổi Commons ngay. Nếu nguyên nhân là tên thuộc tính trong derived query sai, sửa bộ dependency sẽ không giải quyết đúng vấn đề.

Ngược lại, nếu stack trace cho thấy store module gọi một phương thức không tồn tại trong Commons runtime, hãy điều tra tập JAR được chọn trước khi sửa logic nghiệp vụ.

## 13. Tình huống thực hành

### Tình huống A: sửa lỗi bằng cách ghim Commons riêng

Một ứng dụng dùng starter dữ liệu của Boot. Nhóm phát triển thêm dependency Commons trực tiếp với một version lấy từ dự án khác. IDE biên dịch được nhưng ứng dụng lỗi `NoSuchMethodError` khi tạo repository.

Cách phân tích:

1. Xác định version Commons được chọn và nhánh hoặc khai báo quyết định nó.
2. Đối chiếu store module với bộ dependency mà Boot đang quản lý.
3. Xác định có lý do bắt buộc giữ override hay không.
4. Nếu không cần override, đưa dependency trở lại bộ được quản lý rồi kiểm tra đường chạy dữ liệu liên quan.
5. Nếu cần một khả năng ở bộ mới hơn, đánh giá nâng nguồn điều phối hoặc bộ module phù hợp thay vì chỉ thay một JAR.

Điểm cần học là lựa chọn phiên bản phải dựa trên quan hệ của cả bộ, không dựa trên việc một dự án khác từng chạy được với version đó.

### Tình huống B: build thành công nhưng container không chạy

CI dùng JDK mới hơn JVM trong image triển khai. Mã ứng dụng được đặt target thấp, nhưng một dependency được biên dịch cho Java mới hơn runtime. Ứng dụng dừng với lỗi bytecode.

Cần xác định dependency chứa lớp gây lỗi, yêu cầu Java của bộ thư viện và JVM thực tế trong image. Hạ target của mã ứng dụng không chuyển đổi bytecode của dependency. Các lựa chọn là dùng runtime phù hợp hoặc chọn lại bộ thư viện hỗ trợ runtime bắt buộc, sau khi đánh giá yêu cầu chức năng và bảo trì.

### Tình huống C: bộ phiên bản đúng nhưng auditing không chạy

Commons và store module đã nằm trong bộ được quản lý, repository đọc ghi được, nhưng trường người sửa không được điền.

Cần kiểm tra cấu hình auditing của module, nguồn chủ thể và đường ghi có kích hoạt cơ chế auditing hay không. Tính tương thích của dependency không thay thế cấu hình tính năng. Đây là lý do quy trình lựa chọn cần cả dependency graph lẫn kiểm tra hành vi thực tế.

## 14. Câu hỏi tự kiểm tra

### Câu 1: Có thể lấy version của release train để đặt cho mọi module không?

Không. BOM ánh xạ bộ phát hành tới version của từng artifact. Hãy để dependency management áp dụng ánh xạ đó hoặc đối chiếu chính xác khi có nhu cầu quản lý riêng.

### Câu 2: Import BOM có tự thêm store module và cấu hình repository không?

Không. BOM quản lý phiên bản. Dự án vẫn cần khai báo dependency cần dùng và cấu hình hạ tầng tương ứng.

### Câu 3: Vì sao compiler target thấp vẫn có thể gặp `UnsupportedClassVersionError`?

Vì target của mã ứng dụng không thay đổi bytecode đã có trong dependency. JVM runtime phải đáp ứng yêu cầu của toàn bộ lớp được nạp.

### Câu 4: Ứng dụng dùng Boot có nên tự chọn Commons và Framework độc lập không?

Mặc định nên dùng bộ được Boot quản lý. Override cần có căn cứ tương thích và kiểm tra tác động rõ ràng. Nếu nhu cầu đòi hỏi một thế hệ Spring Data khác, hãy đánh giá thay đổi bộ quản lý thay vì chỉ ghim vài artifact.

### Câu 5: Dependency graph đúng đã đủ chứng minh tính năng phân trang và auditing hoạt động chưa?

Chưa. Còn cần module hỗ trợ tính năng, mapping và cấu hình phù hợp, cùng môi trường store đáp ứng yêu cầu. Dependency graph xác nhận tập thư viện; kiểm tra trên đường chạy thực tế xác nhận thêm cấu hình và hành vi.

### Câu 6: Thông tin nào cần lưu cùng quyết định chọn phiên bản?

Nguồn điều phối chính, phiên bản cụ thể của bộ được chọn, lựa chọn Java cho build và runtime, store/provider/driver liên quan, căn cứ tương thích và những override còn hiệu lực. Các thông tin này giúp người bảo trì tái lập môi trường và đánh giá lần nâng cấp tiếp theo.