# Theo dõi release train và thay đổi hợp đồng Commons

## 1. Nâng Spring Data Commons là thay đổi một tập phụ thuộc

Spring Data Commons cung cấp các abstraction dùng chung như Repository, CRUD, derived queries, phân trang, sắp xếp, projection, query by example, mapping metadata và auditing. Các module lưu trữ xây dựng khả năng cụ thể dựa trên phần nền này.

Vì vậy, một thay đổi Commons có thể ảnh hưởng nhiều repository dù mã ứng dụng không gọi trực tiếp class nội bộ nào của Commons. Ngược lại, nâng riêng một JAR Commons không tự nâng được toàn bộ query creator, mapping, driver hoặc hạ tầng transaction của các store.

Cần theo dõi hai lớp thông tin:

- **Bộ phiên bản tương thích:** Spring Boot nếu có, Spring Framework, Spring Data release train, từng module, provider, driver và Java/runtime liên quan.
- **Hợp đồng được ứng dụng sử dụng:** interface repository, chữ ký method, hành vi truy vấn, metadata, callback, auditing và đường chạy AOT/native.

Mục tiêu là biết chính xác bộ phiên bản đang chạy và những hợp đồng nào cần được kiểm chứng khi chuyển sang bộ mục tiêu. Không nên coi việc dự án compile là toàn bộ bằng chứng tương thích.

## 2. Release train và phiên bản module là hai định danh khác nhau

### 2.1. Release train phối hợp các module

Một Spring Data release train tập hợp các phiên bản module được phát hành và phối hợp với nhau. Các thành viên có thể gồm Commons, JPA, MongoDB, JDBC, R2DBC cùng những module khác trong phạm vi train tương ứng.

Train thường được biểu diễn và quản lý bằng Spring Data BOM, có tọa độ Maven:

```text
org.springframework.data:spring-data-bom
```

Module Commons có tọa độ riêng:

```text
org.springframework.data:spring-data-commons
```

Phiên bản của BOM không được mặc định dùng như phiên bản của JAR Commons. Cũng không nên giả định mọi module thành viên đều có số phiên bản giống hệt nhau. Bộ phiên bản do train quản lý mới là thông tin cần đối chiếu.

### 2.2. BOM quản lý phiên bản, không tự thêm mọi dependency

Import một BOM cung cấp các quy tắc quản lý phiên bản cho dependency thuộc phạm vi nó quản lý. Ứng dụng vẫn cần khai báo dependency thực sự sử dụng hoặc nhận chúng qua starter/module khác.

BOM Spring Data cũng không tự cam kết toàn bộ hạ tầng ngoài train đã phù hợp. Java, Spring Framework, persistence provider, driver, database server và công cụ native vẫn cần được xem trong ma trận tương thích liên quan.

Khi dùng Spring Boot, dependency management của Boot thường quản lý một bộ Spring Data phù hợp cùng nhiều thành phần liên quan. Do đó, cần bắt đầu từ bộ được Boot mục tiêu quản lý trước khi quyết định override riêng.

## 3. Chọn một nguồn quản lý phiên bản rõ ràng

### 3.1. Ứng dụng được Spring Boot quản lý

Ví dụ dependency Maven cho ứng dụng JPA dùng dependency management phù hợp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Ví dụ không ghi version trực tiếp trên starter vì giả định project đã được quản lý bởi cấu hình Boot tương ứng. Đoạn dependency riêng lẻ chưa đủ để tạo một project hoạt động nếu phần quản lý phiên bản và hạ tầng khác chưa có.

Trong mô hình này, thêm một version Commons riêng có thể làm lệch bộ đã được chọn. Cần hiểu lý do override, các module chịu ảnh hưởng và bộ test dùng để xác nhận.

### 3.2. Ứng dụng quản lý Spring Data độc lập

Có thể import BOM trong dependency management:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>${spring-data-train.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

```xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jpa</artifactId>
</dependency>
```

`${spring-data-train.version}` là property mà ứng dụng phải xác định từ release train mục tiêu đã được đánh giá tương thích. Ví dụ trình bày cơ chế quản lý, không đưa ra một bộ phiên bản hiện hành để sao chép.

Nếu có nhiều BOM hoặc dependency management ở nhiều tầng, cần xác định phiên bản cuối cùng được resolve. Đọc một dòng version trong file khai báo chưa đủ để biết artifact thực sự dùng ở compile và runtime.

### 3.3. Không ghép bộ bằng cách chọn số mới nhất cho từng JAR

Một bộ gồm Commons mới hơn, module store cũ hơn và provider khác dòng có thể compile một phần nhưng lỗi khi khởi tạo repository hoặc gọi method.

Đặc biệt, override để lấy một method mới trong Commons chưa bảo đảm module store cũ có implementation hoặc query support tương ứng. API xuất hiện trên classpath và khả năng thực thi trên datastore là hai điều phải kiểm chứng riêng.

## 4. Theo dõi thông tin nào cho bộ hiện tại và bộ mục tiêu?

Một bảng đánh giá hữu ích gồm:

| Thành phần | Bộ hiện tại | Bộ mục tiêu | Bằng chứng cần đối chiếu |
| --- | --- | --- | --- |
| Java/runtime | Phiên bản đang build và chạy | Runtime dự kiến | Yêu cầu của Framework, Boot, provider và công cụ build |
| Spring Boot nếu dùng | Dependency management hiện tại | Dòng phát hành mục tiêu | Bộ phụ thuộc được quản lý và hướng dẫn nâng cấp |
| Spring Framework | Phiên bản resolve thực tế | Phiên bản phù hợp mục tiêu | Điều kiện tương thích và thay đổi nền tảng |
| Spring Data train | BOM hoặc bộ được Boot chọn | Train mục tiêu | Thành viên và phiên bản module |
| Commons và module store | Các JAR thực tế | Các phiên bản trong bộ mục tiêu | Release notes và thay đổi API/hành vi |
| Provider/driver | Implementation đang dùng | Bộ tương thích | Mapping, transaction, protocol và yêu cầu runtime |
| AOT/native nếu có | Pipeline và runtime hiện tại | Pipeline mục tiêu | Phạm vi hỗ trợ và kết quả chạy artifact tương ứng |

Bảng là công cụ phân tích; tên train hoặc số phiên bản cụ thể phải lấy từ thông tin chính thức cho bộ đang đánh giá. Không suy ra quan hệ tương thích chỉ từ việc hai version có cùng một vài chữ số.

Cũng cần phân biệt dòng đang được duy trì với dòng đã hết thời gian hỗ trợ. Trạng thái hỗ trợ thay đổi theo thời gian và nhà cung cấp, nên cần xác nhận tại thời điểm ra quyết định thay vì ghi nhớ một mốc cố định.

## 5. Đọc release notes theo hợp đồng ứng dụng đang dùng

### 5.1. Những nguồn cần kết hợp

Khi đánh giá một nâng cấp, nên đối chiếu:

1. Thông tin release train và BOM thành viên.
2. Release notes, migration guide và tài liệu tương ứng phiên bản của Commons.
3. Tài liệu thay đổi của từng module store đang sử dụng.
4. Hướng dẫn của Spring Boot/Framework nếu ứng dụng nâng cùng chúng.
5. Điều kiện của provider, driver và AOT/native toolchain khi liên quan.

Tài liệu phiên bản khác có thể mô tả API không tồn tại trong bộ đang chạy. Cần luôn nối một hướng dẫn với version mục tiêu cụ thể.

### 5.2. Từ thông báo thay đổi tới ảnh hưởng thực tế

Không phải mọi mục trong release notes đều có cùng tác động với ứng dụng. Với mỗi thay đổi liên quan, hãy chuyển thành câu hỏi cụ thể:

- Interface nào của ứng dụng đang kế thừa kiểu bị thay đổi?
- Custom fragment hoặc custom base repository có override chữ ký liên quan không?
- Query method nào dùng từ khóa, property path hoặc kiểu trả về chịu ảnh hưởng?
- Domain model nào phụ thuộc constructor, converter hoặc metadata đang thay đổi?
- Callback và auditing có dựa vào thứ tự hay thời điểm cụ thể không?
- Đường native có cần loại metadata mà phiên bản mới xử lý khác không?

Kết quả mong muốn là một danh sách ảnh hưởng có thể kiểm tra, không chỉ là ghi chú “đã đọc changelog”.

## 6. Hợp đồng tương thích có nhiều lớp

| Lớp hợp đồng | Ví dụ | Bằng chứng cần có |
| --- | --- | --- |
| Source compatibility | Method còn trong interface, generic và kiểu trả về còn phù hợp | Compile mã consumer và các implementation tùy chỉnh |
| Binary compatibility | Class/method runtime khớp với artifact đã dùng khi compile | Bộ dependency resolve và artifact triển khai nhất quán |
| Hành vi API | Kết quả rỗng, lỗi, thứ tự hoặc nhận diện entity mới | Test hành vi trên dữ liệu đại diện |
| Mapping và dữ liệu | Converter, constructor, tên field, ID/version | Đọc dữ liệu cũ và ghi dữ liệu mới theo hợp đồng |
| Query theo store | Toán tử, projection, count, phân trang | Repository integration test trên store phù hợp |
| Cấu hình và bootstrap | Scan, factory, dependency và thời điểm tạo query | Test context cùng cấu hình thực tế |
| AOT/native | Proxy, reflection, resource và kiểu động cần thiết | Build cùng chạy artifact mục tiêu trên các đường liên quan |

Một bản nâng cấp có thể giữ source API nhưng đổi lỗi được phát ra hoặc đường tạo query. Nó cũng có thể compile thành công trong ứng dụng chính nhưng làm một thư viện dùng chung lỗi khi chạy với artifact khác.

Phân loại major, minor hay patch giúp định hướng việc đọc thay đổi, nhưng không thay thế release notes và kiểm chứng. Không mặc định một patch không thể tác động hành vi quan trọng của ứng dụng.

## 7. Ví dụ lịch sử: quan hệ giữa sorting và CRUD thay đổi

Một thay đổi đã xuất hiện từ Spring Data 3.0 là các sorting repository không còn tự kế thừa các CRUD repository tương ứng như trước. Điều này minh họa một thay đổi hợp đồng kế thừa, không chỉ thêm một method mới.

Ví dụ, chỉ khai báo:

```java
interface CustomerRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

không đủ để mặc định có toàn bộ API CRUD trong dòng hợp đồng mới đó. Khi ứng dụng cần cả hai khả năng, có thể khai báo rõ:

```java
interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

Cùng giai đoạn này, `ListCrudRepository` cung cấp các biến thể trả `List` cho các thao tác tương ứng thay vì `Iterable`. Có thể tổ chức một base interface khi bộ mục tiêu hỗ trợ:

```java
@NoRepositoryBean
interface ApplicationRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID> {
}
```

```java
interface CustomerRepository
        extends ApplicationRepository<Customer, Long> {
}
```

Ví dụ dùng các interface của Spring Data Commons, lược bỏ import và mapping của `Customer`. `@NoRepositoryBean` đặt trên interface nền để nó không bị tạo thành repository cụ thể với generic chưa được chốt.

Điều cần rút ra là phải đọc lại hierarchy của abstraction mình dùng. Nếu repository đã kế thừa interface đặc thù store như `JpaRepository`, hãy xem hierarchy của interface đó trong bộ mục tiêu trước khi thêm hoặc thay base interface.

Không sao chép thay đổi này như một quy tắc nâng mọi ứng dụng lên một version cụ thể. Nó là ví dụ cho cách một thay đổi nền có thể ảnh hưởng mã gọi `save`, `findById`, `findAll` hoặc các lớp dùng chung.

## 8. Những hợp đồng Commons cần rà soát có chủ đích

### 8.1. CRUD, generic và phát hiện entity mới

Các implementation tùy chỉnh cần giữ chữ ký generic đúng, ví dụ:

```java
interface ValidatedSave<T> {
    <S extends T> S save(S entity);
}
```

Sau nâng cấp, cần xác nhận fragment/base implementation vẫn được ghép như mong muốn. Không chỉ kiểm tra method có cùng tên.

Với entity có ID gán trước, version hoặc `Persistable.isNew()`, cần kiểm tra trạng thái mới/đã tồn tại được hiểu đúng trong module. Thay đổi ở phần metadata hoặc logic ứng dụng có thể ảnh hưởng đường insert/update và field auditing được điền.

### 8.2. Phân trang và sắp xếp

Rà soát `Page`, `Slice`, `Pageable`, `Sort` cùng các extension đang dùng. Những điều cần giữ gồm nội dung, tổng số phần tử nếu hợp đồng yêu cầu, thứ tự ổn định và cách xử lý trường hợp rỗng.

Nếu bộ mục tiêu cung cấp API scrolling hoặc giới hạn mới, sự xuất hiện của API Commons chưa chứng minh mọi kiểu query ở mọi store đều hỗ trợ. Cần đối chiếu khả năng của module và query cụ thể.

### 8.3. Derived query và query by example

Kiểm tra tên method, toán tử, property traversal và các tham số đặc biệt. Một thay đổi parser có thể làm một tên nhập nhằng được xử lý khác hoặc làm lỗi được phát hiện ở thời điểm khác.

Với query by example, kiểm tra matcher, null, xử lý chuỗi và các thuộc tính bị bỏ qua trên store thực tế. Không chuyển một mô tả API chung thành cam kết về collation hoặc hỗ trợ toán tử của mọi datastore.

### 8.4. Projection, nullability và kiểu trả về

Projection interface, DTO constructor, dynamic projection hoặc annotation nullability có thể ảnh hưởng cách compile, suy luận kiểu và chuyển kết quả. Với Kotlin hoặc code generator, thay đổi metadata kiểu cũng có thể đáng quan tâm dù Java consumer chưa báo lỗi.

Cần xác nhận từng field được map đúng và các trường hợp null/rỗng giữ đúng hợp đồng. Compile thành công không phát hiện mọi sai lệch dữ liệu trả về.

### 8.5. Callback, converter và auditing

Xác định callback nào thuộc Commons SPI, interface nào thuộc module và đường ghi nào kích hoạt chúng. Test nên quan sát kết quả cần thiết, không phụ thuộc chi tiết nội bộ không được cam kết.

Nếu callback chịu trách nhiệm field bắt buộc, hãy kiểm chứng các đường CRUD, custom query và bulk operation liên quan. Không suy ra mọi đường ghi đều dùng cùng lifecycle chỉ vì cùng repository API.

## 9. Phân biệt lỗi lệch bộ với lỗi ứng dụng sau nâng cấp

| Triệu chứng | Giả thuyết nên kiểm tra |
| --- | --- |
| `NoSuchMethodError` | Artifact runtime không cung cấp chữ ký mà code đã compile dựa vào, hoặc có thay đổi binary liên quan |
| `AbstractMethodError` | Interface và implementation không khớp hợp đồng thực thi |
| `ClassNotFoundException` | Kiểu cần tải không có hoặc không được tìm thấy trong cơ chế nạp tương ứng |
| `NoClassDefFoundError` | Có thể thiếu định nghĩa phụ thuộc hoặc đã có lỗi khởi tạo class trước đó; cần đọc cause |
| Lỗi tạo repository/query | Parser, module, cấu hình, model hoặc chữ ký query không phù hợp |
| Kết quả truy vấn khác | Hành vi query/mapping, driver, collation hoặc dữ liệu có thể đã thay đổi |
| JVM chạy nhưng native lỗi | Metadata, resource, proxy hoặc khả năng hỗ trợ AOT/native cần được kiểm tra |

Bảng không phải ánh xạ một exception sang đúng một nguyên nhân. Ví dụ, lỗi class ở native không tự chứng minh chỉ cần thêm reflection hint. Kiểu đó có thể chưa nằm trong dependency hoặc cấu hình build ngay từ đầu.

Trước khi sửa mã nghiệp vụ để chữa `NoSuchMethodError`, nên đối chiếu phiên bản resolve ở compile và runtime, artifact đóng gói và dependency override. Thêm JAR mới nhất một cách ngẫu nhiên có thể tạo thêm lệch bộ.

Ngược lại, một `PropertyReferenceException` sau refactor domain có thể chỉ là tên query sai. Không nên coi mọi lỗi xuất hiện trong đợt nâng cấp đều do release train không tương thích.

## 10. AOT và native là một chiều kiểm chứng riêng

### 10.1. Spring AOT và native image không đồng nhất

Spring AOT xử lý một phần cấu hình và thông tin ứng dụng ở build time, có thể tạo mã hoặc metadata phục vụ mô hình chạy tương ứng. Native image còn có các ràng buộc và toolchain riêng, chẳng hạn quá trình phân tích khả năng truy cập của các kiểu và tài nguyên.

Vì vậy, cần phân biệt:

- Chạy ứng dụng JVM thông thường.
- Chạy theo cấu hình xử lý AOT được bộ phiên bản hỗ trợ.
- Build và chạy native artifact với toolchain mục tiêu.

Một đường chạy thành công không tự chứng minh các đường còn lại đều đúng. Đồng thời, AOT không có nghĩa các thao tác query, mapping hoặc transaction của store được bỏ qua khi runtime.

### 10.2. Các điểm repository cần quan tâm

Những yếu tố có thể liên quan gồm:

- Repository interface và proxy cần thiết.
- Domain type, constructor và property access.
- Projection/DTO được sử dụng trong query.
- Converter, callback và auditing implementation.
- Resource chứa query hoặc cấu hình mà ứng dụng cần khi chạy.
- Kiểu được chọn động theo tên hoặc cấu hình.

Mức framework tự suy ra và mức cần khai báo bổ sung phụ thuộc phiên bản cùng module. Không thêm hint hàng loạt trước khi xác định thiếu thông tin nào và tại sao đường build chưa biết nó.

### 10.3. Cấu hình build cần đại diện cho deployment

Một số quyết định về bean graph và điều kiện cấu hình có thể được xử lý trong quá trình AOT. Cần kiểm tra quy tắc của bộ mục tiêu khi dùng profile hoặc property có thể thay đổi cấu trúc repository và hạ tầng.

Không mặc định mọi thay đổi cấu trúc bean ở runtime sẽ có hiệu lực giống mô hình JVM không qua xử lý AOT. Bộ kiểm chứng phải dùng cấu hình build và cấu hình chạy đại diện cho môi trường triển khai.

Native build thành công vẫn cần chạy các luồng sử dụng repository. Một projection hiếm dùng hoặc converter chỉ được chọn theo một đường dữ liệu có thể không được kiểm chứng bởi smoke test chỉ khởi động ứng dụng.

## 11. Bộ kiểm chứng cho thay đổi hợp đồng

| Nhóm | Ví dụ cần kiểm tra |
| --- | --- |
| Khởi tạo | Repository bean, fragment và query được tạo trong cấu hình mục tiêu |
| CRUD | Tạo, đọc, sửa, xóa; ID/version và trạng thái entity mới |
| Query | Derived query, query khai báo, binding và trường hợp không có dữ liệu |
| Phân trang/sắp xếp | Nội dung, thứ tự, tổng hoặc dấu hiệu còn phần tiếp |
| Projection/QBE | Mapping field và matcher mà store hỗ trợ |
| Lifecycle | Converter, callback, auditing và các đường ghi thay thế |
| Transaction/tài nguyên | Rollback cần thiết, stream được đóng, pipeline reactive giữ phạm vi |
| Dữ liệu cũ | Đọc dữ liệu đã lưu trước nâng cấp và xử lý biểu diễn cũ |
| AOT/native | Các luồng trên trong artifact mục tiêu khi có yêu cầu |

Không cần viết lại mọi test chỉ để lặp chính implementation. Nên chọn dữ liệu đối chứng có thể phát hiện thay đổi hợp đồng quan trọng: tenant khác nhau, giá trị null, hai bản ghi cùng khóa sắp xếp, version cũ hoặc biểu diễn dữ liệu từ phiên bản trước.

Với reactive repository, phải subscribe và quan sát kết quả/lỗi. Với stream, phải tiêu thụ và xác nhận quản lý tài nguyên. Với JPA, một số lỗi ghi chỉ xuất hiện ở flush/commit; test chỉ gọi `save()` chưa chắc bao phủ mốc đó.

Các test dùng mock repository không thực thi parser, mapping hay repository factory. Chúng vẫn có giá trị cho logic service, nhưng cần integration test để kiểm chứng hợp đồng của bộ Spring Data mới.

## 12. Quy trình nâng cấp có thể giải thích và tái hiện

### Bước 1: Chốt bộ đang chạy

Xác định các dependency resolve thực tế, nguồn quản lý phiên bản, các override và artifact triển khai. Ghi rõ runtime JVM hay native cùng cấu hình liên quan.

### Bước 2: Chọn một bộ mục tiêu có quan hệ tương thích rõ

Bắt đầu từ dependency management của Boot nếu dùng, hoặc BOM Spring Data cùng các thành phần nền tương thích. Không chọn rời từng module chỉ theo số phiên bản cao nhất.

### Bước 3: Đọc thay đổi theo khoảng chuyển tiếp

Nếu đi qua nhiều dòng phát hành, xem các thay đổi trung gian liên quan. Một API bị loại ở bộ mục tiêu có thể đã được đánh dấu deprecated trước đó và có hướng chuyển đổi cụ thể.

### Bước 4: Nối thay đổi với mã và hợp đồng ứng dụng

Xác định repository base interface, fragment, query method, domain mapping và đường AOT chịu ảnh hưởng. Mỗi thay đổi cần có cách xác nhận phù hợp.

### Bước 5: Compile và chạy bộ kiểm chứng đại diện

Phân loại lỗi source, lỗi binary, lỗi cấu hình và lỗi hành vi. Giữ query, dữ liệu cùng mức bảo đảm cần thiết để so sánh có ý nghĩa.

### Bước 6: Kiểm chứng artifact triển khai

Đối chiếu dependency đã đóng gói, cấu hình runtime và các luồng dữ liệu quan trọng. Với native, chạy chính artifact native mục tiêu thay vì chỉ test JVM.

### Bước 7: Theo dõi sau triển khai

Quan sát lỗi repository/query, độ trễ, số thao tác store, tỷ lệ retry, allocation và kết quả nghiệp vụ quan trọng. Một bản nâng cấp giữ đúng kết quả vẫn có thể thay đổi query plan hoặc chi phí materialization cần được đánh giá.

## 13. Nâng thư viện khác với chuyển đổi dữ liệu

Một bộ phiên bản mới có thể đọc cùng dữ liệu cũ mà không cần đổi schema, nhưng không được giả định điều đó cho mọi thay đổi model hoặc converter đi kèm.

Những tình huống cần xem riêng gồm đổi tên field lưu trữ, đổi biểu diễn enum/value object, thay loại ID hoặc đổi metadata kiểu được ghi trong một số store. Nếu phiên bản cũ và mới cùng chạy trong giai đoạn rolling deployment, cả hai cần có hợp đồng dữ liệu tương thích trong khoảng chuyển tiếp.

Rollback binary cũng không tự hoàn tác dữ liệu đã được ghi theo biểu diễn mới. Kế hoạch triển khai phải tách quyết định nâng dependency khỏi migration/backfill và quy trình phục hồi dữ liệu khi có liên quan.

Điều này đặc biệt quan trọng khi một converter được thay để hỗ trợ bộ phiên bản mới. Cần biết nó vẫn đọc được dữ liệu cũ hay yêu cầu chuyển đổi có kiểm soát, thay vì chỉ thử với dữ liệu mới tạo trong test.

## 14. Tình huống thực hành

Một thư viện nội bộ chỉ kế thừa `PagingAndSortingRepository`. Một ứng dụng sử dụng thư viện đó vừa nâng bộ Spring Data và thêm override Commons riêng để dùng API mới. Mã gọi `save()` bắt đầu không compile; sau một số sửa chữa, deployment lại báo lỗi method runtime. JVM smoke test qua, nhưng native artifact lỗi khi gọi một projection ít dùng.

Cần tách ít nhất ba lớp vấn đề:

1. Hợp đồng kế thừa của repository base cần được đối chiếu và khai báo đúng nhu cầu CRUD/sorting.
2. Bộ compile/runtime cùng các override phải được kiểm tra để xử lý lệch artifact.
3. Projection và metadata trong đường native cần được kiểm chứng theo toolchain/module mục tiêu.

Sửa interface chỉ giải quyết lớp thứ nhất. Bỏ một override có thể giúp đồng bộ bộ phụ thuộc nhưng không tự chứng minh projection native hoạt động. Mỗi giả thuyết cần bằng chứng ở đúng lớp.

## 15. Bài tập vận dụng

Một hệ thống dùng JPA cho nghiệp vụ và MongoDB cho read model. Nhóm phát triển muốn nâng Commons riêng, giữ nguyên các module store và chỉ chạy unit test mock repository. Ứng dụng còn có custom `save`, query by example, auditing và một tác vụ native đọc DTO theo loại được chọn động.

Hãy đề xuất kế hoạch:

1. Xác định release train và nguồn quản lý phiên bản hiện tại.
2. Chọn bộ mục tiêu và các thành phần ngoài train cần đối chiếu.
3. Lập danh sách hợp đồng của base interface, fragment, query, mapping và auditing.
4. Chọn dữ liệu cùng integration test để phát hiện sai lệch theo từng store.
5. Xác nhận đường JVM/AOT/native cần thiết và các kiểu động thực sự được dùng.
6. Làm rõ khả năng đọc dữ liệu cũ, triển khai đồng thời hai phiên bản và phục hồi nếu cần.

Một lời giải tốt cần chỉ ra version nào được resolve thực tế và vì sao bộ test đủ quan sát các thay đổi liên quan. Chỉ liệt kê dependency mới hoặc thấy ứng dụng khởi động chưa đủ.

## 16. Điểm cần nhớ

Release train giúp phối hợp các module Spring Data; BOM và dependency management giúp chọn bộ phiên bản, nhưng vẫn cần kiểm chứng các hợp đồng ứng dụng sử dụng. Phiên bản train, phiên bản Commons và phiên bản module store là các thông tin cần đối chiếu đúng vai trò.

Theo dõi nâng cấp hiệu quả là nối release notes với repository API, query, mapping, lifecycle và artifact triển khai. Source compatibility, runtime compatibility, dữ liệu cũ và AOT/native là các lớp bằng chứng bổ sung, cần được đánh giá theo khả năng của từng module cùng datastore thực tế.
