# Chiến lược kiểm tra thuộc tính @Id

Trong chương **Phát hiện trạng thái** của **SPRING_DATA_COMMONS**, bài này tập trung vào việc dùng giá trị định danh để suy ra một đối tượng có được xem là mới hay không. Đây là một đầu vào cho cách repository lưu dữ liệu, không phải một phép truy vấn xác nhận bản ghi tồn tại trong kho.

Mục tiêu là hiểu đúng các trường hợp ID chưa gán, ID số không, ID do ứng dụng tự cấp và ID được phục hồi từ dữ liệu đã lưu. Những trường hợp này trông gần giống nhau trong mã Java nhưng có thể dẫn đến nhánh lưu khác nhau.

## 1. “Mới” ở đây có nghĩa gì?

Có ít nhất ba câu hỏi độc lập:

| Câu hỏi | Nguồn thông tin |
| --- | --- |
| Đối tượng Java vừa được tạo bằng new hay đã có từ trước? | Luồng thực thi của ứng dụng |
| Hạ tầng persistence xem đối tượng là mới hay không mới? | Chiến lược state detection |
| Trong kho hiện có bản ghi mang ID này không? | Trạng thái thực của kho dữ liệu |

Một đối tượng vừa được tạo bằng `new` vẫn có thể bị xem là **không mới** nếu nó đã mang ID. Ngược lại, một đối tượng có ID chưa gán có thể được xem là **mới** mà chưa cần đọc kho dữ liệu.

Trong bài, kết quả `isNew = true` nghĩa là “chiến lược đang dùng phân loại đối tượng là mới”. Nó không tự mang các ý nghĩa sau:

- Đã kiểm tra trong cơ sở dữ liệu và không thấy bản ghi.
- ID hợp lệ theo quy tắc nghiệp vụ.
- Thao tác lưu chắc chắn thành công.
- Mọi module sẽ phát ra cùng loại lệnh ghi.

Sự phân biệt này đặc biệt quan trọng khi dùng repository generic hoặc tái sử dụng cùng một thiết kế miền trên các loại kho dữ liệu khác nhau.

## 2. Quy tắc kiểm tra ID mặc định

Khi chiến lược dựa trên ID được áp dụng:

- ID có kiểu tham chiếu và giá trị `null`: đối tượng được xem là mới.
- ID có kiểu số primitive và giá trị `0`: đối tượng được xem là mới.
- Các trường hợp còn lại: đối tượng được xem là không mới.

Quy tắc này được mô tả trong [Entity State Detection Strategies](https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html).

Bảng ví dụ dưới đây giả định không có chiến lược khác thay thế việc kiểm tra ID:

| Kiểu thuộc tính ID | Giá trị | Kết quả theo ID |
| --- | --- | --- |
| `Long` | `null` | Mới |
| `Long` | `0L` | Không mới |
| `Long` | `42L` | Không mới |
| `long` | `0L` | Mới |
| `long` | `42L` | Không mới |
| `Integer` | `null` | Mới |
| `Integer` | `0` | Không mới |
| `int` | `0` | Mới |
| `String` | `null` | Mới |
| `String` | `""` | Không mới |
| `String` | `"ORDER-42"` | Không mới |
| `UUID` | `null` | Mới |
| `UUID` | Một UUID đã được gán | Không mới |

Điểm cần chú ý là **kiểu khai báo của thuộc tính**. `Long` và `long` không có cùng giá trị biểu diễn “chưa có ID”.

Ở tầng abstraction, `AbstractEntityInformation` cũng mô tả cách phân loại dựa trên ID null hoặc ID primitive bằng không. Xem [AbstractEntityInformation API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/AbstractEntityInformation.html).

## 3. @Id đánh dấu định danh, không tự sinh định danh

Annotation của Commons là:

~~~java
import org.springframework.data.annotation.Id;
~~~

Ví dụ khai báo:

~~~java
@Id
private Long id;
~~~

`@Id` xác định thành phần đóng vai trò định danh. Bản thân annotation không quy định rằng ID phải là số tự tăng, UUID, chuỗi ngẫu nhiên hoặc giá trị lấy từ một sequence. Xem [Id API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Id.html).

Có thể tách các trách nhiệm:

| Trách nhiệm | Ví dụ |
| --- | --- |
| Nhận diện thuộc tính định danh | Metadata của @Id |
| Nhận diện trạng thái mới | Kiểm tra giá trị ID theo chiến lược đang dùng |
| Cấp giá trị ID | Cơ sở dữ liệu, module, callback hoặc ứng dụng |
| Kiểm tra tồn tại | Một thao tác đọc phù hợp |
| Bảo đảm không trùng khóa | Ràng buộc và hành vi của kho dữ liệu |

Nếu ứng dụng chỉ thêm `@Id` lên một field rồi chờ mọi kho tự sinh được giá trị đúng kiểu, thiết kế còn thiếu chính sách cấp ID.

Với JPA, annotation định danh thuộc namespace `jakarta.persistence.Id` và chiến lược sinh khóa theo JPA là vấn đề riêng. Không đổi annotation giữa Commons và JPA chỉ vì chúng có cùng tên ngắn.

## 4. Vì sao Long nullable thường rõ ràng hơn long cho ID được cấp khi lưu?

Với kiểu primitive:

~~~java
@Id
private long id;
~~~

Một instance chưa gán field có `id = 0`. Giá trị không này được dùng làm dấu hiệu “chưa có định danh” trong chiến lược primitive tương ứng.

Với wrapper:

~~~java
@Id
private Long id;
~~~

Một instance chưa gán field có `id = null`. Trạng thái chưa được cấp khóa có thể biểu diễn tách biệt với một giá trị số thực sự.

Sai lầm phổ biến là:

~~~java
@Id
private Long id = 0L;
~~~

Ứng dụng đã chuyển từ primitive sang wrapper nhưng vẫn dùng số không làm dấu hiệu chưa lưu. Theo kiểm tra ID, field này không null nên đối tượng được xem là không mới.

Tương tự, nếu constructor hoặc bộ ánh xạ request thay `null` bằng `0L`, trạng thái persistence có thể thay đổi dù người viết chỉ muốn “tránh null”.

Cần thống nhất quy ước ở mọi đường tạo đối tượng:

- Factory tạo mới.
- Constructor hoặc builder.
- Chuyển đổi từ DTO.
- Phục hồi dữ liệu.
- Sao chép và thay đổi đối tượng immutable.

Không dùng một hàm chung kiểu `id == null || id == 0` cho mọi kiểu ID rồi coi đó là quy tắc của Spring Data. Hàm đó làm mất sự khác biệt giữa `Long` và `long`.

## 5. Ví dụ riêng cho Spring Data JDBC: khóa được cấp khi insert

Phần này dùng Spring Data JDBC để minh họa một vòng đời cụ thể. Nó không phải cam kết rằng mọi module lưu trữ đều thực hiện giống JDBC.

### 5.1. Mô hình miền

~~~java
package com.acme.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("catalog_item")
public final class CatalogItem {

    @Id
    private final Long id;

    private final String sku;

    public CatalogItem(Long id, String sku) {
        this.id = id;
        this.sku = sku;
    }

    public static CatalogItem newItem(String sku) {
        return new CatalogItem(null, sku);
    }

    public CatalogItem withId(Long id) {
        return new CatalogItem(id, this.sku);
    }

    public CatalogItem withSku(String sku) {
        return new CatalogItem(this.id, sku);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

Mô hình không có thuộc tính version và không triển khai `Persistable`. Vì vậy ví dụ tập trung vào việc kiểm tra ID.

Constructor cần metadata tên tham số phù hợp để phục hồi đối tượng. `withId` và constructor đầy đủ cung cấp đường tạo instance chứa định danh sau khi khóa được cấp. Những phương thức sao chép phải giữ các giá trị không thay đổi.

### 5.2. Repository

~~~java
package com.acme.catalog;

import org.springframework.data.repository.CrudRepository;

public interface CatalogItemRepository
        extends CrudRepository<CatalogItem, Long> {
}
~~~

Ví dụ giả định ứng dụng đã cấu hình Spring Data JDBC, datasource, transaction manager và phạm vi quét repository. Nếu có nhiều module repository cùng hiện diện, cần phân biệt rõ repository thuộc module nào.

Một bảng tương ứng theo cú pháp PostgreSQL có thể là:

~~~sql
CREATE TABLE catalog_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL
);
~~~

DDL chỉ minh họa chính sách cấp khóa ở cơ sở dữ liệu. Khi dùng hệ quản trị khác, cần cú pháp và cấu hình tương ứng.

### 5.3. Tạo mới rồi cập nhật

~~~java
CatalogItem candidate = CatalogItem.newItem("BOOK-01");

CatalogItem saved = repository.save(candidate);

CatalogItem changed = saved.withSku("BOOK-02");

CatalogItem updated = repository.save(changed);
~~~

Biến `repository` giả định được inject dưới kiểu `CatalogItemRepository`.

Ý nghĩa từng bước:

| Thời điểm | ID trong instance đang xét | Phân loại theo ID |
| --- | --- | --- |
| Sau newItem | null | Mới |
| Sau lần lưu thành công và nhận instance trả về | Giá trị khóa đã được cấp | Không mới |
| Sau withSku trên instance đã lưu | Giữ khóa đã cấp | Không mới |

Spring Data JDBC sử dụng trạng thái mới để chọn insert cho aggregate mới và đường cập nhật cho aggregate không mới. Với cột tự tăng được cấu hình phù hợp, khóa trả về được đưa vào đối tượng sau insert. Xem [Persisting Entities của Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html).

Không giả định `candidate` ban đầu đã bị sửa tại chỗ. Mô hình trong ví dụ là immutable nên ứng dụng phải tiếp tục từ kết quả `saved`.

Hợp đồng `CrudRepository.save` yêu cầu sử dụng instance trả về cho các thao tác tiếp theo vì instance có thể được thay thế. Xem [CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

## 6. Một đối tượng Java mới vẫn có thể là entity không mới

Xét một bản ghi đã lưu có ID `42`. Ứng dụng nhận dữ liệu từ nơi khác và tạo lại đối tượng:

~~~java
CatalogItem reconstructed = new CatalogItem(42L, "BOOK-03");
~~~

`reconstructed` là instance Java vừa được cấp phát, nhưng ID không null nên chiến lược ID xem nó là không mới.

Điều này hợp lý nếu ứng dụng đang phục hồi một định danh đã có. Tuy nhiên, nó không chứng minh rằng:

- Bản ghi 42 hiện còn tồn tại.
- Dữ liệu SKU đang dùng là phiên bản mới nhất.
- Người gọi có quyền thay đổi bản ghi.
- Những field khác không bị mất trong quá trình dựng lại đối tượng.

Cũng không dùng `equals`, `hashCode` hoặc so sánh tham chiếu để suy ra nhánh state detection. Một đối tượng khác tham chiếu nhưng giữ cùng ID vẫn có thể đại diện cho cùng định danh persistence.

Với thao tác cập nhật nghiệp vụ cần kiểm tra tồn tại, một luồng thường rõ ràng là tải đối tượng theo ID, xử lý trường hợp không tìm thấy, áp dụng thay đổi rồi lưu kết quả. Luồng ấy cung cấp dữ liệu cho nghiệp vụ; nó không biến phép kiểm tra ID thành một truy vấn tồn tại.

## 7. ID do ứng dụng tự gán: giới hạn quan trọng của chiến lược

Ví dụ một đơn hàng được cấp UUID ngay trong ứng dụng:

~~~java
package com.acme.orders;

import java.util.UUID;

import org.springframework.data.annotation.Id;

public final class AssignedOrder {

    @Id
    private final UUID id;

    private final String description;

    public AssignedOrder(UUID id, String description) {
        this.id = id;
        this.description = description;
    }

    public static AssignedOrder create(String description) {
        return new AssignedOrder(UUID.randomUUID(), description);
    }

    public UUID getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }
}
~~~

Lời gọi:

~~~java
AssignedOrder order = AssignedOrder.create("Đơn hàng đầu tiên");
~~~

Đối tượng vừa được tạo để lưu lần đầu, nhưng UUID đã khác null. Nếu chỉ kiểm tra ID, kết quả là không mới.

Mâu thuẫn nằm ở hai quy ước khác nhau:

~~~text
Nghiệp vụ:
    Chưa từng lưu → muốn tạo bản ghi mới

Chiến lược ID:
    ID đã có giá trị → không mới
~~~

Chiến lược ID không thể tự biết UUID vừa được cấp trong bộ nhớ hay vừa đọc từ kho. Cả hai tình huống đều có một giá trị UUID khác null.

Điều tương tự xảy ra với:

- Mã khách hàng dạng `"CUS-100"`.
- Số khóa lấy trước từ một dịch vụ cấp số.
- ID từ hệ thống nguồn trong quá trình nhập dữ liệu.
- Khóa nghiệp vụ được xác định trước khi ghi.

### Những hướng thiết kế phù hợp

| Nhu cầu | Hướng cần cân nhắc |
| --- | --- |
| Khóa được kho cấp tại lần ghi đầu | Giữ trạng thái chưa gán phù hợp trước khi lưu |
| ID được gán trước nhưng cần theo dõi vòng đời mới | Chiến lược Persistable hoặc metadata tùy biến được module hỗ trợ |
| Mô hình thật sự cần optimistic locking | Kiểm tra vai trò của thuộc tính version theo module |
| Use case yêu cầu insert tường minh | API insert của module nếu có |
| Use case yêu cầu upsert | API upsert và điều kiện hỗ trợ của kho |

Không thêm version chỉ như một mẹo để vượt qua vấn đề ID. Version có ý nghĩa về cạnh tranh cập nhật và cần vòng đời phù hợp.

Với `Persistable`, ứng dụng phải quản lý trạng thái mới sau khi lưu và sau khi đọc lại; callback hoặc cơ chế chuyển trạng thái phải thuộc đúng module. Không sao chép callback của JPA vào một mô hình JDBC rồi mặc định nó sẽ được thực thi.

Spring Data JDBC có `JdbcAggregateTemplate.insert` và `update` để chọn thao tác tường minh, bỏ qua bước phân loại mới của `save`. Đây là lựa chọn riêng của module được mô tả trong [Template API của Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html).

## 8. Giá trị rỗng và giá trị không hợp lệ không được xử lý như null

Ví dụ:

~~~java
@Id
private String id = "";
~~~

Chuỗi rỗng là một đối tượng String khác null. Chiến lược kiểm tra ID không mặc định coi nó là chưa có khóa.

Tương tự:

~~~java
@Id
private Long id = -1L;
~~~

`-1L` vẫn là một giá trị khác null. Việc ứng dụng quy ước số âm là “tạm thời” không làm Spring Data tự hiểu quy ước ấy.

Cần phân biệt:

| Quy tắc | Câu hỏi |
| --- | --- |
| State detection | Giá trị có phù hợp dấu hiệu “chưa có ID” của chiến lược không? |
| Validation | ID có đúng định dạng hoặc miền giá trị được phép không? |
| Mapping | ID có chuyển đổi được sang kiểu của kho không? |
| Ràng buộc lưu trữ | Giá trị có được kho chấp nhận và có bị trùng không? |

Ví dụ, một String khác null có thể bị phân loại không mới nhưng vẫn bị ứng dụng từ chối vì không đúng mẫu mã đơn hàng. Hai kết quả không mâu thuẫn vì chúng phục vụ hai mục đích khác nhau.

Không tự trim, đổi chữ hoa/thường hoặc thay đổi giá trị ID tại nhiều tầng khác nhau. Nếu hệ thống có chuẩn hóa khóa, cần một chính sách nhất quán để thao tác tìm, lưu và đối chiếu cùng hiểu một định danh.

## 9. Không mới chưa xác định câu lệnh ghi cuối cùng

Commons cung cấp abstraction chung; module lưu trữ quyết định dùng kết quả nhận diện như thế nào.

| Module hoặc API | Điều cần hiểu |
| --- | --- |
| Spring Data JDBC repository save | Trạng thái mới và không mới điều khiển đường insert hoặc cập nhật aggregate |
| Spring Data JPA repository save | Lựa chọn giữa EntityManager.persist và EntityManager.merge theo metadata trạng thái |
| MongoTemplate save | Có hành vi lưu có thể tạo document nếu đối tượng chưa có trong kho |

Spring Data JPA mô tả việc chọn `persist` hoặc `merge` trong [Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html). Không đồng nhất `merge` với lời cam kết “chỉ có một SQL UPDATE”, vì JPA provider còn xử lý trạng thái và vòng đời persistence.

MongoDB mô tả sự khác nhau giữa insert và save tại [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html). Đặc biệt, cần xét thêm version, điều kiện cập nhật và API cụ thể trước khi suy ra kết quả.

Hệ quả thực hành: một đối tượng có ID tự gán có thể đi qua API save thành công ở một module nhưng không chứng minh thiết kế state detection ấy phù hợp khi chuyển sang module khác.

Không dùng một kết quả thử nghiệm trên một kho để khẳng định `save` luôn là upsert trong toàn bộ Spring Data.

Cũng không suy rằng `isNew = true` có thể bỏ qua ràng buộc khóa. Nếu thao tác insert dùng một ID đã có, kho vẫn có thể từ chối do trùng định danh.

## 10. Kiểm tra tồn tại trước không sửa được chiến lược ID

Xét đoạn minh họa cho mô hình JDBC ở phần 5:

~~~java
Long chosenId = 900L;

if (!repository.existsById(chosenId)) {
    CatalogItem candidate = new CatalogItem(chosenId, "BOOK-09");
    repository.save(candidate);
}
~~~

Dù `existsById` trả false, candidate vẫn có ID khác null. Không có phép gán nào trong đoạn mã làm chiến lược ID đổi kết quả thành mới.

Phép đọc tồn tại và phép phân loại mới là hai thao tác khác nhau. Thêm một câu đọc trước không tự thay đổi metadata hoặc trạng thái của đối tượng.

Đoạn mã còn có khoảng thời gian giữa kiểm tra và ghi:

~~~text
Luồng A: kiểm tra ID chưa tồn tại
Luồng B: tạo bản ghi mang ID đó
Luồng A: thực hiện thao tác ghi
~~~

Do đó, kiểm tra trước có thể hữu ích cho phản hồi nghiệp vụ nhưng không thay thế ràng buộc và cơ chế xử lý cạnh tranh của kho.

Nếu yêu cầu là “tạo nếu chưa có”, cần xác định đúng ngữ nghĩa: insert và xử lý trùng khóa, upsert theo điều kiện, hay một cơ chế khác được module hỗ trợ. Không đổi tên phương thức service thành `create` rồi coi đó là bảo đảm về hành vi repository.

## 11. Giới hạn phạm vi: khi nào việc kiểm tra ID bị thay thế?

Các bảng đầu bài nói về **chiến lược ID đang có hiệu lực**, không phải mọi entity bất kể cấu hình.

Hai tình huống cần nhận diện:

- Một thuộc tính version có thể được dùng để suy ra trạng thái trước khi rơi về ID.
- Với entity triển khai `Persistable`, hạ tầng có thể giao việc quyết định cho `isNew()`.

Các lựa chọn được mô tả tại [Entity State Detection Strategies](https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html).

Vì vậy, nếu một đối tượng có ID khác null nhưng vẫn được nhận diện mới, trước khi kết luận có lỗi hãy kiểm tra xem nó có version hoặc triển khai `Persistable` hay không.

Quy tắc cụ thể vẫn cần đọc theo module. Ví dụ Spring Data JPA ưu tiên thuộc tính version không phải primitive; primitive version không dùng để nhận diện mới theo cùng quy ước của những module khác. Điểm khác biệt này được giải thích trong [chiến lược state detection của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html).

Các annotation hoặc field nghiệp vụ như `createdAt`, `status = DRAFT` hay `wasSaved` không tự có vai trò state detection nếu không có cơ chế tích hợp tương ứng.

Tương tự, một đối tượng được trả về từ derived query, Query by Example hoặc một trang kết quả thường có ID do mapping cung cấp, nhưng tên kiểu truy vấn không phải tiêu chí nhận diện mới.

## 12. Giữ định danh đúng qua các đường tạo và sao chép

Trong ứng dụng thực tế, lỗi thường xuất hiện ngoài repository:

| Đường đi | Lỗi có thể phát sinh |
| --- | --- |
| DTO tạo mới sang entity | Gán Long bằng 0 thay vì null |
| DTO cập nhật sang entity | Bỏ mất ID nên đối tượng bị xem là mới |
| Factory sao chép | Giữ ID cũ khi mục tiêu thật sự là tạo một thực thể khác |
| Wither hoặc mapper immutable | Quên mang theo ID đã được cấp |
| Import dữ liệu | Gán ID nguồn nhưng vẫn dựa vào quy tắc ID null để insert |
| Tiếp tục dùng object cũ sau save | Object cũ còn ID null nên lần lưu tiếp theo lại bị xem là mới |

Không đặt lại ID về null như một cách buộc cập nhật phải thành insert mà không xác định nghiệp vụ. Thao tác ấy có thể tạo một thực thể khác thay vì thay đổi thực thể hiện tại.

Nếu nghiệp vụ thật sự cần nhân bản, hãy có một factory hoặc luồng clone rõ ràng: chọn thuộc tính cần sao chép, cấp định danh mới theo chính sách và xử lý các liên kết liên quan.

Với một API cập nhật, cần phân biệt định danh của đối tượng đang sửa với dữ liệu có thể thay đổi. Đừng để quá trình ánh xạ request vô tình làm mất hoặc thay định danh rồi để repository suy ra một ý định khác.

Đối với audit, việc bản ghi được tạo hay cập nhật cũng có thể ảnh hưởng field người tạo, người sửa và thời điểm. Khi gặp dữ liệu audit bất thường, cần kiểm tra cả state detection và cơ chế auditing cụ thể, không chỉ logic gán timestamp trong service.

## 13. Cách chẩn đoán và kế hoạch kiểm chứng

Khi một lần lưu đi vào nhánh ngoài dự kiến, nên quan sát theo trình tự:

1. Xác định repository hoặc template thuộc module nào.
2. Xác định thuộc tính định danh mà metadata thực sự dùng.
3. Kiểm tra kiểu khai báo: Long hay long, String hay UUID.
4. Ghi nhận giá trị ID ngay trước thao tác lưu.
5. Kiểm tra version, Persistable hoặc metadata tùy biến.
6. Xác nhận dữ liệu của instance trả về sau lưu.
7. Quan sát thao tác lưu và dữ liệu trong kho theo API thực tế.

Không chẩn đoán chỉ bằng câu “tôi vừa new đối tượng”. Cũng không giả định ID trong request giống ID của instance cuối cùng được truyền vào repository.

Bảng dưới là kế hoạch kiểm chứng cho người học, chưa phải kết quả chạy thử kèm bài:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Long ID null, chỉ dùng chiến lược ID | Được xem là mới |
| Long ID bằng 0, chỉ dùng chiến lược ID | Được xem là không mới |
| long ID bằng 0 | Được xem là mới theo quy tắc primitive |
| String ID rỗng | Không bị coi là null |
| UUID được cấp tại factory | Không mới theo kiểm tra ID đơn thuần |
| Đối tượng dựng lại với ID đã có | Cấp phát Java mới không làm đổi phân loại |
| Lưu thành công với khóa tự sinh | Instance trả về có khóa và không còn mới theo ID |
| Bản ghi bị xóa sau khi tải | ID không tự thay đổi để phản ánh việc bản ghi đã mất |
| Kiểm tra existsById trước save | Không tự sửa phân loại của candidate |
| Thêm version hoặc Persistable | Xác định lại chiến lược thực sự đang có hiệu lực |

Một phép thử tự viết lại công thức `id == null` chỉ kiểm tra công thức của mã thử. Để kiểm chứng hành vi ứng dụng, cần dùng metadata hoặc đường lưu của module thực tế.

Với thử nghiệm tích hợp, nên kiểm tra cả ID trước/sau, dữ liệu được lưu và loại thất bại mong đợi nếu bản ghi không tồn tại hoặc trùng khóa. Tránh chỉ khẳng định rằng phương thức save được gọi.

## 14. Bài thực hành: hai cách cấp định danh

Thiết kế hai mô hình độc lập:

1. `CatalogItem` dùng Long nullable, khóa được cơ sở dữ liệu cấp.
2. `ExternalOrder` dùng mã String được cấp trước trong ứng dụng.

Với mỗi mô hình, mô tả:

- Giá trị ID trước lần lưu đầu.
- Kết quả nhận diện nếu chỉ kiểm tra ID.
- API lưu phù hợp với ý định tạo mới hoặc cập nhật.
- Giá trị và instance cần tiếp tục sử dụng sau lưu.
- Hành vi mong đợi khi ID trùng hoặc bản ghi cập nhật đã bị xóa.

Riêng `ExternalOrder`, phải giải quyết rõ khoảng cách giữa “đã có mã” và “đã được lưu”. Chọn cơ chế trạng thái hoặc thao tác lưu thích hợp của module, thay vì thay ID bằng chuỗi rỗng hoặc thêm một lần existsById rồi mặc định vấn đề đã được giải quyết.
