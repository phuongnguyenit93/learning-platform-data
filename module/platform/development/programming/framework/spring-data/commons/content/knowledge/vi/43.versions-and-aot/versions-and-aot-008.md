# AOT repository, generated accessor và phạm vi store hỗ trợ

## 1. Mục tiêu và phạm vi bài học

Trong module `SPRING_DATA_COMMONS`, ta tìm hiểu các abstraction dùng chung của Spring Data như Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing. Bài này thuộc chương **Phiên bản và AOT**, tập trung vào việc các abstraction ấy được chuẩn bị như thế nào khi ứng dụng dùng xử lý ahead-of-time.

Sau bài học, bạn cần phân biệt được ba vấn đề thường bị gọi chung là “Spring Data có AOT”:

1. Hạ tầng repository được phân tích và chuẩn bị trước khi ứng dụng chạy.
2. Mã hoặc metadata phục vụ repository, truy vấn và truy cập thuộc tính được tạo ở một thời điểm cụ thể.
3. Một store và phiên bản cụ thể hỗ trợ được những khả năng nào khi chạy trên JVM hoặc trong native image.

Ba vấn đề liên quan với nhau nhưng không đồng nghĩa. Có một lớp accessor được sinh ra chưa đủ để kết luận repository đã được tối ưu bằng AOT; chạy được native image cũng chưa chứng minh mọi truy vấn đã được sinh thành mã tại build time.

Bài học trình bày nguyên tắc và cách đánh giá khả năng hỗ trợ. Những chi tiết phụ thuộc release, như danh sách store có bộ sinh repository AOT hoặc tên tùy chọn bật tối ưu, phải được đối chiếu với đúng phiên bản dùng trong dự án. Không lấy một kết luận của một release áp dụng mặc định cho toàn bộ Spring Data.

## 2. AOT là gì trong ngữ cảnh Spring Data?

**Ahead-of-time processing** là việc chuyển một phần công việc vốn thực hiện khi khởi động hoặc trong quá trình chạy sang giai đoạn build. Spring AOT phân tích cấu hình ứng dụng và tạo các artifact để runtime sử dụng. Native-image compilation là một bước khác, dù thường dùng đầu ra của Spring AOT.

Trong ứng dụng Spring Data, công việc khởi tạo có thể gồm:

- Phát hiện interface repository và xác định domain type, ID type.
- Phân tích chữ ký phương thức và phân loại phương thức CRUD, query method hoặc phương thức thuộc custom fragment.
- Chuẩn bị metadata cho mapping, projection và những đường truy cập phản chiếu cần thiết.
- Chuẩn bị cấu hình bean và các runtime hint phù hợp.
- Với store và release có hỗ trợ riêng, tạo thêm mã hoặc biểu diễn truy vấn từ những thông tin đã biết khi build.

AOT chỉ chuyển được phần việc có đủ đầu vào tĩnh. Nó không truy vấn dữ liệu của người dùng trong lúc build và không biến mọi quyết định lúc chạy thành hằng số.

| Đầu vào hoặc công việc | Có thể chuẩn bị trước? | Phần vẫn thuộc runtime |
| --- | --- | --- |
| Interface `ProductRepository` đã được đăng ký | Có thể phân tích kiểu và phương thức | Lấy bean và gọi phương thức |
| Tên derived query cố định | Có thể phân tích, tùy bộ xử lý và store | Bind giá trị tham số và thực thi truy vấn |
| Projection đã biết từ chữ ký | Có thể chuẩn bị thông tin kiểu và hint phù hợp | Tạo kết quả từ dữ liệu thực tế |
| `Pageable`, `Sort` của request | Có thể biết kiểu tham số | Giá trị trang, kích thước và hướng sắp xếp |
| Người dùng đang đăng nhập để auditing | Có thể chuẩn bị hạ tầng auditing | Xác định auditor tại thời điểm thao tác |
| Dữ liệu trong database | Không phải dữ liệu tĩnh của AOT | Đọc, ghi, kiểm tra ràng buộc và transaction |

Một lợi ích tiềm năng là giảm công việc khởi tạo hoặc giúp runtime có đủ thông tin khi khả năng khám phá động bị giới hạn. Mức cải thiện thực tế phụ thuộc ứng dụng; cần đo đạc thay vì suy ra từ việc có thư mục generated sources.

## 3. Ba cơ chế cần tách biệt

### 3.1. Chuẩn bị hạ tầng Spring bằng AOT

Đây là lớp chuẩn bị bean, metadata và hint cho cấu hình ứng dụng được phân tích. Runtime hint mô tả các nhu cầu như reflection, resource hoặc proxy để công cụ liên quan có thể xử lý chúng đúng cách.

Một runtime hint không phải bản triển khai thuật toán nghiệp vụ. Hint cho phép đọc constructor không có nghĩa constructor đó đã được thay bằng lời gọi trực tiếp trong mọi đường thực thi.

### 3.2. Tối ưu repository hoặc query tại build time

Ở lớp này, bộ xử lý của store có thể dùng metadata repository để tạo artifact phục vụ khởi tạo hoặc thực thi. Mức độ sinh mã, các loại query được xử lý và cơ chế fallback phụ thuộc store và release.

Không nên suy diễn rằng “AOT repository” luôn có nghĩa:

- Mỗi interface được thay hoàn toàn bằng một lớp Java viết sẵn.
- Mọi repository proxy đều biến mất.
- Mọi `@Query`, expression hay custom fragment đều được dịch hoàn toàn tại build time.
- Database sẽ dùng một execution plan đã được đóng gói trong ứng dụng.

AOT phía ứng dụng và việc database lập kế hoạch thực thi là hai công việc khác nhau. Driver, database và tham số thực tế vẫn tham gia khi truy vấn chạy.

### 3.3. Generated accessor trong mapping

Spring Data Commons có abstraction để mô tả persistent entity và persistent property. Một số đường mapping dùng accessor hoặc entity instantiator được sinh để giảm chi phí truy cập reflection lặp lại trên JVM.

Cần hỏi ngay: **mã được sinh vào lúc nào?**

- Sinh hoặc định nghĩa lớp trong lúc ứng dụng đang chạy là code generation tại runtime.
- Sinh artifact trong quy trình build AOT là code generation tại build time.
- Có metadata hoặc hint để dùng reflection là một khả năng khác nữa.

Từ “generated” tự nó không chỉ ra thời điểm sinh, cũng không bảo đảm tương thích native image.

## 4. Hình dung vòng đời từ repository đến database

```text
Interface repository + domain type + cấu hình ứng dụng
                         |
                         v
               Giai đoạn build có AOT
       Phân tích bean/repository và metadata đã biết
       Chuẩn bị hint, mã hoặc query artifact nếu được hỗ trợ
                         |
                         v
                Artifact của ứng dụng
         Chạy trên JVM hoặc được biên dịch native
                         |
                         v
                      Runtime
       Gọi repository -> bind tham số -> truy vấn store
       -> mapping/projection -> trả kết quả cho ứng dụng
```

Không phải mọi ô trong sơ đồ đều do Spring Data Commons thực hiện. Commons cung cấp hợp đồng và hạ tầng chung; module của store, Spring Framework, driver và công cụ build đảm nhận các phần tương ứng.

Thông tin tồn tại lúc build cũng phải phù hợp với cấu hình triển khai. Một repository chỉ được đăng ký bởi cấu hình không xuất hiện trong quá trình AOT có thể không nằm trong tập artifact được chuẩn bị. Không nên coi cấu hình bean đã được phân tích như cấu hình động tùy ý sau khi build.

## 5. Ví dụ repository: phần nào tĩnh, phần nào động?

Giả sử domain `Product` có các thuộc tính `id`, `name`, `status` và `createdAt`. Repository dùng các hợp đồng của Commons:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    Page<Product> findByStatus(ProductStatus status, Pageable pageable);

    List<Product> findByNameStartingWith(String prefix, Sort sort);
}
```

Ví dụ giả định store đang dùng hỗ trợ các keyword, kiểu trả về và tham số đặc biệt tương ứng. Việc có cùng abstraction trong Commons không tạo ra cùng tập tính năng cho mọi store. Annotation mapping của `Product` được chọn theo store và không thể suy ra chỉ từ interface trên.

Các thông tin tĩnh gồm:

- Domain type `Product` và ID type `Long`.
- Tên thuộc tính `status`, `name` và cấu trúc tên phương thức.
- Kiểu trả về `Page<Product>` hoặc `List<Product>`.
- Sự xuất hiện của `Pageable` và `Sort` trong chữ ký.

Các thông tin động gồm:

- `status` được chọn trong một request cụ thể.
- Giá trị `prefix` mà người dùng tìm kiếm.
- Trang hiện tại, kích thước trang và thuộc tính sắp xếp được yêu cầu.
- Dữ liệu, transaction và phản hồi của database.

Nếu bộ xử lý AOT của store hỗ trợ derived query này, nó có thể tận dụng phần tĩnh. Điều đó không loại bỏ việc kiểm tra đầu vào và bind tham số khi gọi repository.

Ví dụ gọi:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Product> page = repository.findByStatus(
        ProductStatus.ACTIVE,
        PageRequest.of(0, 20, Sort.by("createdAt").descending()));
```

Các điểm cần giữ đúng khi giải thích kết quả:

- Chỉ số trang trong `PageRequest` bắt đầu từ `0`.
- Trả về `Page` có nhu cầu thông tin tổng số phần tử; tùy đường thực thi, store có thể cần thêm count query. Không khẳng định luôn có đúng hai truy vấn trong mọi trường hợp.
- AOT không tự tạo index cho `status` hay `createdAt`.
- Thuộc tính được phép sort nên được kiểm soát ở biên ứng dụng; AOT không thay thế quy tắc xác thực request.

## 6. Generated accessor: truy cập thuộc tính không đồng nghĩa truy vấn

### 6.1. Accessor giải quyết việc gì?

Giả sử mapping layer cần đặt `id` sau khi lưu hoặc đọc một thuộc tính khi chuyển đối tượng sang biểu diễn của store. Nó cần cơ chế truy cập thuộc tính của entity.

Ở mức khái niệm, Spring Data Commons cung cấp các kiểu như:

- `PersistentEntity`: metadata mô tả một persistent entity.
- `PersistentProperty`: metadata của một thuộc tính.
- `PersistentPropertyAccessor`: hợp đồng đọc hoặc cập nhật thuộc tính qua metadata.
- `EntityInstantiator`: cơ chế tạo đối tượng entity từ thông tin được cung cấp.

Các hợp đồng này phục vụ mapping. Chúng không chịu trách nhiệm tự tạo câu truy vấn cho `findByStatus`.

```text
Repository query
    -> lấy dữ liệu từ store
    -> mapping dữ liệu thành entity
       -> chọn constructor / instantiator
       -> truy cập thuộc tính khi cần
    -> trả entity hoặc projection
```

Chuỗi này chỉ là mô hình khái niệm. JPA provider, chẳng hạn, có cơ chế materialization riêng, nên không được áp nguyên xi mọi tối ưu mapping của Commons cho entity JPA.

### 6.2. Generated instantiator và generated property accessor khác nhau

| Cơ chế | Công việc chính | Ví dụ |
| --- | --- | --- |
| Entity instantiator | Tạo một entity từ các giá trị đầu vào | Gọi constructor nhận `id`, `name`, `status` |
| Property accessor | Đọc hoặc cập nhật thuộc tính trên entity | Gán ID được store sinh ra nếu mapping cần |
| Repository/query artifact | Chuẩn bị hoạt động của phương thức repository | Chuẩn bị phần tĩnh của derived query được hỗ trợ |

Một entity được tạo hoàn toàn qua constructor có thể cần ít thao tác population sau khởi tạo. Vì vậy, tối ưu accessor không tự động là điểm quan trọng nhất trong mọi mô hình dữ liệu.

### 6.3. Các điều kiện truy cập ảnh hưởng tới sinh mã

Khả năng dùng tối ưu sinh mã có thể bị ảnh hưởng bởi:

- Mức truy cập của lớp, constructor, thuộc tính và phương thức.
- Lớp lồng nhau, lớp nội bộ và cách tham chiếu đối tượng bao ngoài.
- Khả năng định nghĩa lớp trong class loader tương ứng.
- Quy tắc truy cập package hoặc Java module.
- Mô hình immutable và cơ chế cập nhật được mapping layer nhận biết.
- Giới hạn của môi trường runtime.

Không nên biến các yếu tố trên thành quy tắc tuyệt đối kiểu “mọi field phải public”. Field private không đồng nghĩa mọi tối ưu đều bị vô hiệu; cách truy cập cụ thể phụ thuộc implementation và môi trường. Cần xem điều kiện của đúng cơ chế, đúng phiên bản.

Nếu không dùng được một đường sinh mã, một số đường mapping trên JVM có thể dùng reflection thay thế. Khả năng fallback này không tự bảo đảm native image sẽ chạy: các thành phần phản chiếu cần thiết vẫn phải được giữ lại và được mô tả phù hợp.

## 7. Immutable entity và ý nghĩa của việc cập nhật thuộc tính

Xét một kiểu immutable ở mức minh họa:

```java
public final class Product {

    private final Long id;
    private final String name;

    public Product(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Product withId(Long id) {
        return new Product(id, this.name);
    }
}
```

Đây là ví dụ về hình dạng đối tượng, chưa phải cấu hình mapping hoàn chỉnh cho một store cụ thể. Constructor, annotation và quy ước phải đáp ứng yêu cầu của module đang sử dụng.

Khi đường mapping có hỗ trợ cập nhật immutable entity bằng phương thức `with…`, việc “đặt ID” có thể tạo đối tượng mới. Accessor của cơ chế đó có thể cần giữ tham chiếu đến bean thay thế.

Hệ quả thực hành: khi lưu entity, nên dùng đối tượng repository trả về để làm việc tiếp theo:

```java
Product saved = repository.save(new Product(null, "Bàn phím"));
Long generatedId = saved.getId();
```

Ví dụ này giả định `ProductRepository` tương ứng và store đã được cấu hình sinh ID. Nó không có nghĩa mọi store sinh ID giống nhau hoặc hỗ trợ nguyên trạng lớp minh họa trên.

AOT không làm đối tượng immutable trở thành mutable. Nó cũng không tự bổ sung một đường khởi tạo mà mô hình dữ liệu chưa cung cấp.

## 8. Phạm vi hỗ trợ phải được tách theo từng tầng

Một câu hỏi hữu ích không phải chỉ là “store này có AOT không?”, mà là “với tổ hợp phiên bản này, tính năng nào được hỗ trợ ở tầng nào?”.

| Tầng cần đánh giá | Câu hỏi cần trả lời | Không thể suy ra chỉ từ tầng này |
| --- | --- | --- |
| Spring Framework AOT | Bean và cấu hình nào được phân tích trước? | Toàn bộ query của store đã được sinh trước |
| Spring Data Commons | Hạ tầng repository và metadata chung tham gia thế nào? | Mọi module kế thừa cùng một bộ sinh query |
| Module store | Query, projection, fragment và mapping nào được hỗ trợ? | Driver hoặc provider cũng đã đáp ứng native |
| Mapping/provider | Entity được khởi tạo, truy cập và theo dõi ra sao? | Repository đã thay hoàn toàn proxy |
| Driver và thư viện liên quan | Chúng hoạt động trong môi trường đích không? | Luồng nghiệp vụ của ứng dụng đã được kiểm chứng |
| Ứng dụng | Custom code và cấu hình triển khai có đủ thông tin không? | Một build thành công bảo đảm mọi request thành công |

### 8.1. Các nhóm store cần được đánh giá riêng

| Nhóm module | Điểm cần xem xét riêng |
| --- | --- |
| Spring Data JPA | Khả năng tối ưu repository/query của đúng release; giới hạn query; xử lý entity và native của JPA provider |
| Spring Data JDBC | Đường mapping aggregate, khởi tạo đối tượng, dialect và khả năng của driver JDBC |
| Spring Data MongoDB | Mapping document, converter tùy chỉnh, projection, query và driver tương ứng |
| Spring Data R2DBC | Query và mapping reactive, driver R2DBC, chuỗi thực thi thực tế khi có subscription |
| Các module khác | Tài liệu AOT/native của chính module và các thư viện mà module dùng |

Bảng này là bản đồ trách nhiệm, không phải danh sách chứng nhận hỗ trợ. Không được đọc dòng JPA thành “mọi query JPA đều được AOT”, hay dòng R2DBC thành “mọi driver reactive đều chạy native”.

Một store có thể hỗ trợ ứng dụng native thông qua hint và metadata nhưng chưa có cùng khả năng sinh query/repository như một store khác. Ngược lại, một tối ưu build time dùng được trên JVM không có nghĩa mọi thư viện đi kèm ứng dụng đều dùng được trong native image.

### 8.2. Ma trận phiên bản nên ghi theo tổ hợp

Khi đánh giá một ứng dụng cụ thể, ghi lại ít nhất:

| Thành phần | Thông tin cần cố định |
| --- | --- |
| Java | Phiên bản JDK và môi trường chạy |
| Spring Boot nếu có | Phiên bản và tập dependency được quản lý |
| Spring Framework | Phiên bản thực sự được resolve |
| Spring Data | Release train, Commons và module store thực sự được resolve |
| Thư viện store | Provider, driver và những extension quan trọng |
| AOT/native toolchain | Công cụ và phiên bản thực hiện xử lý/build |
| Chế độ kiểm chứng | JVM thông thường, JVM dùng artifact AOT, hoặc native executable |

Nên dùng tổ hợp dependency được hệ sinh thái hỗ trợ. Việc ép riêng một phiên bản Commons mới vào module store cũ không tạo ra một môi trường AOT được bảo đảm tương thích.

## 9. Các abstraction dùng chung chịu ảnh hưởng ra sao?

### 9.1. CRUD

`CrudRepository` định nghĩa hợp đồng thao tác cơ bản. Các quy tắc như entity mới hay đã tồn tại, transaction và optimistic locking vẫn phụ thuộc mapping và store.

AOT không biến `save` thành thao tác bỏ qua validation, cũng không thay đổi ý nghĩa nghiệp vụ của `deleteById` chỉ vì có lớp generated.

### 9.2. Derived queries và query khai báo

Với derived query, cấu trúc tên phương thức là đầu vào tĩnh phù hợp để phân tích. Tuy nhiên, keyword được hỗ trợ và cách dịch sang ngôn ngữ truy vấn vẫn do module store quyết định.

Với query khai báo, cần phân biệt phần query cố định với expression, tham số và lựa chọn phụ thuộc runtime. Tùy release, bộ xử lý có thể hỗ trợ một phần, có fallback hoặc từ chối những trường hợp cụ thể. Không tự giả định cơ chế nào khi chưa có tài liệu cho tổ hợp đang dùng.

### 9.3. Phân trang và sắp xếp

`Pageable` và `Sort` là hợp đồng chung; cách triển khai limit, offset, count hoặc sort do store đảm nhận. Chuẩn bị trước metadata không loại bỏ chi phí offset lớn, count đắt hoặc thiếu index.

Nếu có sort động, cần thử đúng các thuộc tính mà ứng dụng cho phép. Một query mặc định chạy thành công không đại diện cho mọi tổ hợp sort.

### 9.4. Projection

Interface projection, DTO projection và dynamic projection không phải cùng một đường thực thi. Chúng có thể cần proxy, constructor hoặc thông tin phản chiếu khác nhau.

Ví dụ dynamic projection:

```java
<T> List<T> findByStatus(ProductStatus status, Class<T> type);
```

Kiểu kết quả được chọn ở runtime, nên cần xem bộ xử lý có nhận biết được tập kiểu kết quả hay không và store hỗ trợ đường này tới đâu. Không nên cho phép tên lớp tùy ý từ request rồi kỳ vọng AOT tự phát hiện mọi lớp có thể được chọn.

### 9.5. Auditing

Hạ tầng auditing có thể được chuẩn bị trước, nhưng auditor và thời gian ghi nhận là thông tin runtime. Với reactive auditing, ngữ cảnh xác định auditor còn phải phù hợp mô hình reactive được sử dụng.

Generated accessor chỉ có thể là một phần trong đường cập nhật thuộc tính auditing. Nó không thay thế cấu hình bật auditing, nguồn auditor hoặc callback/listener do store yêu cầu.

### 9.6. Custom repository fragment và converter

AOT không tự hiểu mọi hành vi động bên trong custom fragment hoặc converter. Nếu mã tự chọn lớp qua chuỗi tên, đọc resource động hoặc dùng reflection riêng, ứng dụng phải bảo đảm công cụ build nhận biết các nhu cầu đó.

Cách làm dễ kiểm soát hơn là biểu diễn rõ các implementation và kiểu dữ liệu được hỗ trợ trong cấu hình, đồng thời kiểm chứng các đường thực thi ấy ở môi trường đích.

## 10. JVM có AOT và native image khác nhau ở đâu?

| Khía cạnh | JVM thông thường | JVM dùng artifact AOT | Native image |
| --- | --- | --- | --- |
| Thời điểm chuẩn bị | Nhiều việc ở startup/runtime | Một phần đã chuyển sang build | Dùng phân tích và artifact build để tạo executable |
| Sinh lớp lúc chạy | Thường khả thi trong giới hạn JVM | Vẫn phụ thuộc cơ chế thực tế | Không thể mặc định dựa vào sinh bytecode tùy ý như trên JVM |
| Reflection/proxy/resource | Có thể khám phá động trong nhiều trường hợp | Cần xem đường thực thi và cấu hình AOT | Phải đáp ứng yêu cầu phân tích và đăng ký tương ứng |
| Kết nối database | Runtime | Runtime | Runtime |
| Dữ liệu và transaction | Runtime | Runtime | Runtime |
| Cần kiểm thử nghiệp vụ | Có | Có | Có |

Native image thường dựa trên giả định tập chương trình có thể phân tích tại build time. Vì vậy, những hành vi chỉ xuất hiện sau khi triển khai cần được mô hình hóa hoặc đăng ký phù hợp; không thể dựa hoàn toàn vào việc classpath tình cờ có một lớp.

Điều này cũng giải thích vì sao fallback reflection thành công trên JVM chưa đủ làm bằng chứng cho native. Cần kiểm chứng đúng artifact sẽ được triển khai.

## 11. Quy trình đánh giá cho một ứng dụng thực tế

Quy trình sau là hướng dẫn áp dụng sau bài học, không giả định rằng các bước build hoặc chạy đã được thực hiện cho dự án hiện tại.

### Bước 1: Cố định tổ hợp phiên bản

Ghi lại các thành phần trong ma trận phiên bản. Dùng tài liệu của đúng release và module để xác định khả năng được công bố, điều kiện bật và giới hạn.

Tránh dựa vào một bài viết của release khác hoặc suy luận chỉ từ tên class có hậu tố `Aot`.

### Bước 2: Liệt kê các đường repository quan trọng

Một danh sách gọn có thể bao gồm:

- CRUD và ID do store sinh.
- Derived query có tham số.
- `Page` cùng filter và sort được ứng dụng sử dụng.
- Projection interface hoặc DTO đang xuất hiện trong API.
- Dynamic projection nếu có.
- Custom fragment, converter và auditing.
- Với reactive repository, luồng phải có subscription để thực thi.

Mục đích là bám theo tính năng thật của ứng dụng, không tạo một ma trận thử nghiệm vô hạn.

### Bước 3: Xác định artifact AOT thực sự được sử dụng

Đọc đầu ra build và cấu hình của công cụ tương ứng để biết AOT processing đã chạy và artifact đã được tích hợp vào đầu ra triển khai. Việc chỉ thấy source generated tồn tại chưa đủ chứng minh runtime đang dùng nó.

Không sửa trực tiếp mã generated để vá lỗi. Thay đổi phải nằm ở source, cấu hình hoặc dependency tạo ra artifact đó, rồi được tái tạo theo quy trình build.

### Bước 4: Chạy luồng dữ liệu trên môi trường đích

Một kiểm chứng có giá trị cần đi qua thao tác repository thực tế: lưu, đọc, truy vấn và kiểm tra kết quả. Với `Page`, xem cả thông tin tổng số phần tử khi nghiệp vụ sử dụng nó. Với auditing, kiểm tra giá trị auditor và timestamp.

Một phép thử chỉ khởi tạo application context chưa chạm đến converter hiếm dùng, projection động hoặc nhánh query chỉ được kích hoạt khi nhận tham số nhất định.

### Bước 5: Đo đúng lợi ích cần đạt

Nếu mục tiêu là startup hoặc bộ nhớ, đo các đại lượng ấy trên cùng điều kiện và dữ liệu. Nếu mục tiêu là tốc độ query, phân tích cả số lượt round-trip, index, execution plan và mapping.

Tối ưu accessor không sửa được việc tải quá nhiều dữ liệu. AOT cũng không tự giải quyết N+1 hay một count query đắt.

## 12. Chẩn đoán theo triệu chứng

| Triệu chứng | Hướng kiểm tra đầu tiên | Điều chưa nên kết luận |
| --- | --- | --- |
| AOT build không phân tích được query method | Keyword, thuộc tính domain, kiểu trả về và giới hạn bộ xử lý của store | Toàn bộ module store không hỗ trợ AOT |
| JVM chạy được, native thiếu constructor hoặc kiểu | Đường reflection/instantiation, hint và loại được lựa chọn động | Đổi mọi field sang public sẽ xử lý được |
| Lỗi proxy của projection | Kiểu projection thực tế, hỗ trợ store và cấu hình cho môi trường đích | Mọi projection đều không được hỗ trợ |
| Không dùng generated accessor | Điều kiện lớp, constructor, class loader và đường mapping thực tế | Repository AOT chắc chắn đang tắt |
| JPA entity không theo cơ chế accessor đang kỳ vọng | Trách nhiệm của JPA provider và mapping của provider | Commons phải thực hiện mọi thao tác đọc ghi entity |
| Query trả dữ liệu sai dù build thành công | Điều kiện query, bind tham số, mapping, sort và transaction | Build AOT đã kiểm chứng logic nghiệp vụ |
| Native khởi động được nhưng lỗi khi gọi fragment | Reflection, resource hoặc thư viện do custom code dùng | Kiểm tra startup đã bao phủ fragment |
| Startup giảm nhưng query vẫn chậm | Database, network, index, lượng dữ liệu và mapping | AOT phải làm mọi thao tác repository nhanh hơn |

Ưu tiên xác định tầng xảy ra lỗi. Một lỗi do driver hoặc provider có thể xuất hiện khi gọi repository nhưng không vì thế trở thành lỗi sinh query của Commons.

## 13. Tình huống áp dụng: API danh mục sản phẩm

Một API có các yêu cầu:

1. Đọc danh sách sản phẩm đang hoạt động, trả `Page`.
2. Chỉ cho phép sort theo `name` và `createdAt`.
3. Trả DTO gồm ID và tên.
4. Ghi người cập nhật cuối cùng khi chỉnh sửa sản phẩm.
5. Triển khai cùng logic dưới dạng native executable.

Cách đánh giá hợp lý:

- Chốt store và tổ hợp dependency trước khi lựa chọn khả năng AOT của repository.
- Kiểm tra query, phân trang và DTO projection theo tài liệu của module đó.
- Xác nhận đường tạo DTO, cập nhật immutable entity nếu có, và auditing hoạt động trong artifact đích.
- Kiểm soát tập sort tại tầng nhận request rồi chuyển sang `Sort` hợp lệ.
- Kiểm tra request cập nhật có auditor đúng và request danh sách có tổng số phần tử phù hợp.
- Đo startup riêng với thời gian phản hồi truy vấn; dùng quan sát database để nhận diện count query hoặc vấn đề index.

Giả sử API khởi động native thành công nhưng DTO projection lỗi ở request đầu tiên. Kết luận đúng là luồng projection chưa được đáp ứng trong cấu hình thực tế. Chưa đủ bằng chứng để nói CRUD, toàn bộ repository AOT hay toàn bộ store đều không được hỗ trợ.

Giả sử API chạy đúng nhưng không dùng generated accessor của Commons. Cần xác định store và mapping layer có đi qua cơ chế đó không. Với đường dữ liệu do provider riêng quản lý, tìm kiếm một accessor cụ thể của Commons có thể không phải cách đánh giá phù hợp.

## 14. Câu hỏi tự kiểm tra

1. Một lớp accessor được sinh tại runtime có phải là bằng chứng đã bật build-time AOT không?
2. Vì sao nhận `Pageable` không có nghĩa truy vấn và trang kết quả đã được tính trong lúc build?
3. Store chạy được native có đồng nghĩa store đó có mọi tối ưu repository AOT không?
4. Vì sao cần phân biệt entity instantiator với property accessor?
5. Vì sao đường reflection fallback trên JVM vẫn cần kiểm chứng ở native image?
6. Khi dùng JPA, vì sao không thể mặc định toàn bộ mapping đi qua accessor của Commons?
7. Khi gặp lỗi một dynamic projection, cần khoanh vùng điều gì trước khi kết luận về hỗ trợ AOT?

### Gợi ý trả lời

1. Không. Phải xác định thời điểm sinh và cách artifact được runtime sử dụng.
2. Build có thể biết chữ ký và cấu trúc; tham số phân trang, dữ liệu và kết quả thuộc runtime.
3. Không. Hỗ trợ native, hint, repository generation và query generation là những khả năng cần kiểm tra riêng.
4. Instantiator tạo đối tượng; accessor đọc hoặc cập nhật thuộc tính, có thể trên một đối tượng thay thế khi mapping hỗ trợ immutable entity.
5. Môi trường native cần biết các nhu cầu động phù hợp khi build; việc JVM tự khám phá được không bảo đảm điều kiện ấy đã có.
6. JPA provider chịu trách nhiệm quan trọng về materialization và truy cập trạng thái entity theo cơ chế của provider.
7. Kiểu projection được chọn, chữ ký phương thức, giới hạn store/release và metadata hoặc hint cho đường thực thi cụ thể.

## 15. Những nguyên tắc cần nhớ

- Hỏi rõ **chuẩn bị cái gì**, **vào lúc nào**, **bởi thành phần nào** khi nghe cụm từ AOT.
- Commons cung cấp hợp đồng chung; phạm vi tối ưu cụ thể còn phụ thuộc module store và release.
- Generated accessor phục vụ truy cập thuộc tính trong mapping, khác với sinh artifact cho repository hoặc query.
- Hỗ trợ native cần được đánh giá trên cả ứng dụng, provider, driver và custom code.
- Kết luận hỗ trợ phải gắn với tổ hợp phiên bản và luồng repository đã được kiểm chứng.