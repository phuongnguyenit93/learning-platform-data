# Phân biệt hợp đồng CRUD với cơ chế insert/update/merge của từng store

## 1. Cùng gọi save nhưng không có một cơ chế ghi chung cho mọi store

Một service có thể gọi:

```java
Product saved = products.save(product);
```

Từ lời gọi này, bạn biết ứng dụng đang yêu cầu lưu một Product và nhận lại kết quả. Nhưng chỉ nhìn tên `save` chưa đủ để biết:

- Có insert hay update trong cơ sở dữ liệu hay không.
- Store nhận diện đối tượng mới bằng cách nào.
- Có tải trạng thái hiện tại trước khi ghi hay không.
- Instance đầu vào có trở thành đối tượng được quản lý hay không.
- Các trường null có bị ghi đè vào dữ liệu cũ hay không.
- Thay đổi đã được flush hoặc commit ở thời điểm nào.

Module **SPRING_DATA_COMMONS** cung cấp các abstraction dùng chung như repository và CRUD. Store module đưa các hợp đồng đó đến một công nghệ lưu trữ cụ thể. Provider, driver và kho dữ liệu tiếp tục quyết định phần thực thi bên dưới.

Bài này giúp bạn đọc đúng ranh giới đó, tránh coi `save` là tên khác của một câu SQL UPDATE hoặc một lệnh upsert phổ quát.

## 2. Hợp đồng CRUD và thao tác vật lý ở hai tầng khác nhau

### 2.1. Hợp đồng của save

Trong `CrudRepository<T, ID>`:

```java
<S extends T> S save(S entity);
```

Ở cấp ứng dụng:

- Đối tượng truyền vào phải khác null.
- Người gọi nhận đối tượng sau khi lưu theo cơ chế của repository.
- Cần sử dụng giá trị trả về vì instance hoặc trạng thái có thể khác đầu vào.
- Lỗi ràng buộc, xung đột đồng thời hoặc hạ tầng vẫn có thể xảy ra.

Chữ ký không có tham số “chỉ insert” hoặc “chỉ update”. Nó cũng không cam kết một câu lệnh hay một lượt mạng.

### 2.2. Các từ dễ bị dùng lẫn

| Khái niệm | Ý nghĩa |
| --- | --- |
| CRUD | Nhóm năng lực tạo, đọc, cập nhật, xóa ở cấp hợp đồng |
| `save` | Phương thức repository yêu cầu lưu một đối tượng |
| Insert | Tạo dữ liệu mới theo cơ chế của store |
| Update | Thay đổi dữ liệu đã tồn tại theo điều kiện và ngữ nghĩa của store |
| Upsert | Cơ chế kết hợp cập nhật hoặc tạo mới theo điều kiện do API/store quy định |
| JPA `persist` | Đưa entity mới vào vòng đời quản lý của persistence context |
| JPA `merge` | Hợp nhất trạng thái đối tượng vào entity được quản lý và trả về entity đó |
| SQL MERGE | Một câu lệnh của cơ sở dữ liệu có ngữ nghĩa riêng theo hệ quản trị |

JPA `merge` không đồng nghĩa câu lệnh SQL MERGE. Provider có thể thực hiện nhiều thao tác để đáp ứng một lời gọi merge.

Tương tự, một đường lưu có khả năng tạo mới khi chưa có dữ liệu không làm toàn bộ hợp đồng CrudRepository trở thành API upsert có cùng bảo đảm ở mọi store.

### 2.3. Bốn tầng cần lần theo

```text
Ý định nghiệp vụ
  "tạo sản phẩm" hoặc "đổi giá sản phẩm"
              |
              v
Hợp đồng repository
  save(product)
              |
              v
Store module và metadata
  phát hiện trạng thái, chọn đường ghi, áp dụng mapping
              |
              v
Provider/driver và kho dữ liệu
  câu lệnh, kiểm soát đồng thời, ràng buộc, commit
```

Không nên nhảy thẳng từ chữ `save` đến kết luận “chắc chắn chạy một UPDATE”.

## 3. Phát hiện đối tượng mới không phải luôn kiểm tra tồn tại trong database

### 3.1. Vì sao cần nhận diện trạng thái?

Một store module có thể cần chọn giữa các đường thực thi khác nhau cho:

- Đối tượng được coi là mới.
- Đối tượng được coi là đã có trạng thái lưu trữ.

Để làm điều đó, hạ tầng sử dụng metadata và quy tắc phát hiện trạng thái. Các dấu hiệu thường gặp là ID, version hoặc cơ chế `Persistable.isNew()`.

Không được mặc định mọi lời gọi save đều chạy một truy vấn tồn tại trước rồi mới quyết định.

### 3.2. ID là một dấu hiệu, không phải bằng chứng tuyệt đối

| Tình huống | Vì sao ID chưa đủ để suy luận |
| --- | --- |
| ID null | Có thể phù hợp đối tượng mới, nhưng vẫn cần chiến lược cấp ID hợp lệ |
| ID đã có giá trị | Có thể là ID tự cấp cho đối tượng mới |
| ID từng được cấp nhưng transaction rollback | Đối tượng Java có ID nhưng dữ liệu có thể chưa commit |
| ID đến từ request | Người gửi có thể chỉ định một bản ghi không tồn tại |
| ID đúng nhưng version cũ | Bản ghi tồn tại nhưng cập nhật có thể bị từ chối |

“ID khác null” và “bản ghi chắc chắn tồn tại” là hai mệnh đề khác nhau.

### 3.3. Quy tắc theo module phải được đọc riêng

Không giả định thứ tự ưu tiên ID, version và cờ trạng thái giống nhau ở mọi store.

Ví dụ, Spring Data JPA thường ưu tiên thuộc tính version kiểu không nguyên thủy nếu có; nếu không có loại version phù hợp, nó dựa vào ID theo cơ chế mặc định. Domain thực hiện Persistable có thể cung cấp quyết định isNew riêng.

Các module khác có cơ chế tích hợp tương ứng nhưng vẫn cần xem quy tắc và kiểu dữ liệu được hỗ trợ trong đúng phiên bản.

Việc hiểu điểm này giúp tránh viết một base repository generic mang giả định sai rằng “chỉ cần getId() khác null là luôn update”.

## 4. Spring Data JPA: save chọn persist hoặc merge

### 4.1. Luồng khái niệm

Với implementation cơ sở JPA thông thường, có thể hình dung:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}

return entityManager.merge(entity);
```

Đây là mã rút gọn để giải thích việc chọn đường thực thi, không phải implementation thay thế để chép vào một repository chung.

Spring Data JPA chọn đường dựa trên thông tin entity. JPA provider như Hibernate xử lý vòng đời entity và sinh SQL theo mapping, trạng thái và dialect.

### 4.2. Persist không chỉ có nghĩa “thực thi INSERT ngay bây giờ”

`persist` đưa entity mới vào persistence context. Câu lệnh insert có thể được thực hiện ở thời điểm do provider và chiến lược định danh yêu cầu.

Một số chiến lược cần tương tác sớm với cơ sở dữ liệu để có ID; các thay đổi khác có thể chờ flush.

Vì vậy:

- Gọi persist không đồng nghĩa đã commit.
- Có ID không đồng nghĩa transaction đã hoàn tất.
- Thời điểm xuất hiện SQL không chỉ do tên method của repository quyết định.

### 4.3. Merge không làm đối tượng detached tự trở thành managed

Giả sử có một đối tượng detached:

```java
Product detached = ...;

Product managed = products.save(detached);
```

Nếu đường lưu sử dụng merge, trạng thái từ detached được hợp nhất vào instance được quản lý. Người gọi phải dùng `managed` như kết quả của thao tác lưu.

Hai tham chiếu có thể khác nhau:

```text
detached ── sao chép/hợp nhất trạng thái ──> managed
                                                |
                                                v
                                  persistence context quản lý
```

Việc tiếp tục sửa đối tượng detached sau đó không tự bảo đảm thay đổi tiếp tục được theo dõi chỉ vì bạn đã gọi save trước đó.

Nếu đối tượng đã là managed trong context, hành vi identity có thể khác. Không dùng một quan sát trong trường hợp đó để suy ra quy tắc cho mọi đầu vào.

### 4.4. Merge không bảo đảm chỉ UPDATE

Provider có thể cần đọc dữ liệu, lấy entity được quản lý, xử lý quan hệ và đồng bộ thay đổi.

Nếu ID không tồn tại, kết quả còn phụ thuộc trạng thái mà hệ thống xác định, mapping ID/version và quy tắc của JPA provider. Một số tình huống có thể dẫn đến tạo dữ liệu; các tình huống xác định entity detached nhưng không còn bản ghi có thể bị báo lỗi.

Không dựa vào merge như một cách phổ quát để “có thì update, chưa có thì insert”. Nếu nghiệp vụ yêu cầu chính xác một trong hai hành vi, cần thiết kế API và ràng buộc tương ứng.

## 5. Đọc trạng thái entity JPA để hiểu hành vi save

| Trạng thái khái niệm | Đặc điểm | Điều cần lưu ý |
| --- | --- | --- |
| Mới, chưa được quản lý | Đối tượng được tạo trong ứng dụng, chưa tham gia context | Cần được nhận diện mới đúng cách |
| Managed | Được persistence context quản lý | Thay đổi có thể được dirty checking theo dõi |
| Detached | Từng có trạng thái lưu trữ nhưng không còn được context hiện tại quản lý | Save có thể đi qua merge; dùng kết quả trả về |
| Removed | Được đánh dấu xóa trong context | Không tự xem như một đối tượng mới để save lại |

Đây là các khái niệm JPA. Không mang nguyên mô hình managed/detached và dirty checking sang MongoDB hoặc Spring Data JDBC.

### 5.1. Sửa một entity managed

Trong một transaction JPA phù hợp:

```java
Product product = products.findById(id)
        .orElseThrow();

product.changePrice(newPrice);
```

Nếu Product đang managed, provider có thể phát hiện thay đổi và ghi khi flush mà không cần một lần save chỉ để kích hoạt dirty checking.

Ứng dụng vẫn có thể giữ lời gọi repository.save theo cách tổ chức hợp đồng, nhưng cần hiểu rằng cơ chế theo dõi thay đổi đến từ JPA/provider.

Điều này không có nghĩa chỉ sửa một đối tượng đọc từ repository là đủ để ghi trong mọi store.

### 5.2. Dựng entity từ một request cập nhật một phần

Giả sử database đang có:

```text
id = 42
sku = KEY-001
name = Bàn phím cơ
price = 1200000
```

Request chỉ muốn đổi giá. Nếu mapper dựng một Product có id 42, giá mới nhưng name và sku là null rồi gọi save, merge không tự hiểu null mang nghĩa “không thay đổi”.

Những giá trị đó có thể tham gia trạng thái được hợp nhất, làm dữ liệu cũ bị ghi đè hoặc khiến ràng buộc bị vi phạm.

Với cập nhật một phần, hãy phân biệt “không gửi trường” với “chủ ý đặt trường thành null”. Domain/service hoặc API update của store phải thực hiện đúng quy tắc đó.

## 6. Version và Persistable ảnh hưởng việc chọn đường lưu

### 6.1. Version không chỉ phục vụ kiểm soát đồng thời

Trong JPA, một thuộc tính version kiểu không nguyên thủy có thể được dùng trong quy tắc phát hiện đối tượng mới mặc định:

```java
import jakarta.persistence.Version;

@Version
private Long version;
```

Với cơ chế thông thường của Spring Data JPA:

- Nếu có thuộc tính version phù hợp và giá trị là null, entity được xem là mới.
- Nếu không có loại version được dùng cho quyết định đó, ID được xem xét.
- Version nguyên thủy không biểu đạt null nên không được dùng theo cùng cách để phân biệt trạng thái mới.

Một entity có ID tự cấp nhưng version null có thể đi theo đường persist. Vì vậy không được chỉ xem ID rồi đoán chắc chắn merge.

Ngược lại, mapper cập nhật làm mất version có thể làm quyết định trạng thái sai với ý định của request. Không nên dựng lại entity thiếu dữ liệu rồi trông chờ save tự đoán đầy đủ ngữ cảnh.

JPA dùng annotation version của persistence API tương ứng. Không tự thay mọi annotation version giữa các store chỉ vì chúng có cùng tên ngắn.

### 6.2. Persistable cung cấp quyết định isNew

Commons có interface:

```java
import org.springframework.data.domain.Persistable;
```

Khi store tích hợp cơ chế này, domain có thể cung cấp `getId()` và `isNew()` thay cho việc chỉ dựa vào suy luận mặc định.

Ví dụ JPA với ID do ứng dụng cấp:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;

import org.springframework.data.domain.Persistable;

@Entity
public class AssignedProduct implements Persistable<String> {

    @Id
    private String id;

    private String sku;

    @Transient
    private boolean newEntity = true;

    protected AssignedProduct() {
    }

    public AssignedProduct(String id, String sku) {
        this.id = id;
        this.sku = sku;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Cờ newEntity không được lưu như một thuộc tính nghiệp vụ. Các callback cập nhật nó theo vòng đời JPA.

Mẫu này minh họa việc một đối tượng có ID vẫn có thể được đánh dấu mới. Nó không phải chiến lược mặc định cần thêm vào mọi domain.

### 6.3. isNew là trách nhiệm cần giữ nhất quán

Nếu tạo lại AssignedProduct từ một request có ID của bản ghi đang tồn tại, constructor vẫn đặt newEntity bằng true. Khi đó đường persist có thể được chọn và gặp lỗi thay vì cập nhật.

Callback cũng không biến trạng thái trong bộ nhớ thành bằng chứng commit. Sau một lỗi hoặc rollback, cần xem lại vòng đời đối tượng trước khi dùng lại.

Chỉ dùng Persistable khi bạn có cách quản lý trạng thái mới/cũ rõ ràng cho các đường tạo, tải, chuyển đổi, retry và lưu.

Không viết `isNew()` luôn true chỉ để ép mọi lời gọi thành insert. Khi domain đã tồn tại, chiến lược đó vi phạm ý định lưu và có thể tạo lỗi trùng định danh.

## 7. MongoDB: insert, save và việc thay thế trạng thái document

### 7.1. Không có persistence context theo mô hình JPA

Spring Data MongoDB ánh xạ domain object sang document. Bạn không nên giả định một document đọc về rồi bị sửa trong bộ nhớ sẽ tự được dirty checking ghi lại như entity managed của JPA.

Cần một thao tác ghi phù hợp để chuyển thay đổi xuống store.

Repository vẫn có thể cung cấp save và saveAll theo hợp đồng quen thuộc. Nhưng implementation không đi qua EntityManager hoặc JPA merge.

### 7.2. Phân biệt đường insert và save

Trong cơ chế repository MongoDB thông thường, quyết định đối tượng mới ảnh hưởng việc chọn thao tác insert hoặc save tương ứng.

Ở API MongoDB của Spring Data:

- Insert biểu đạt việc tạo document mới; định danh hoặc khóa duy nhất trùng có thể gây lỗi.
- Save với định danh đã có, trong đường không version phù hợp, có thể ghi trạng thái vào document theo định danh và tạo document khi chưa có.
- Mapping version có thể làm đường ghi trở thành một cập nhật có điều kiện thay vì một upsert không kiểm tra xung đột.

Các hành vi này phải được đọc theo API và mapping cụ thể. Không suy từ khả năng tạo khi chưa có của một đường save rằng mọi lời gọi repository save đều giống nhau.

### 7.3. Ví dụ với ID do ứng dụng cấp

Giả sử một ProductDocument có:

```text
id = P-001
sku = KEY-001
name = Bàn phím cơ
price = 1200000
```

Nếu object có ID, không có version và quy tắc trạng thái chọn đường save, việc ID chưa có trong collection không nhất thiết khiến lời gọi thất bại. Đường save tương ứng có thể tạo document theo cơ chế của nó.

Nếu nghiệp vụ là “chỉ được tạo mới”, hãy chọn thao tác insert hoặc thiết kế create tương ứng, với ràng buộc định danh và khóa duy nhất phù hợp.

Nếu nghiệp vụ là “chỉ cập nhật khi document đã có”, cần một thao tác hoặc điều kiện cập nhật thể hiện yêu cầu đó, rồi kiểm tra kết quả. Không coi sự có mặt của ID trên object là kiểm tra tồn tại.

### 7.4. Save không phải patch tự động

Giả sử document đang có name, sku, price và các trường khác. Request chỉ đưa ID và giá mới.

Nếu dựng một object thiếu các trường còn lại rồi đưa vào đường save, trạng thái document có thể bị thay thế hoặc ghi lại theo biểu diễn được mapping. Không mặc định trường không gửi sẽ được giữ nguyên.

Khi yêu cầu là cập nhật một vài trường, cân nhắc update theo trường bằng API của store, chẳng hạn điều kiện và các phép cập nhật được hỗ trợ. Thiết kế đó khác với việc lưu toàn bộ trạng thái object.

Cần xác định rõ:

- Trường không có trong request.
- Trường chủ ý đặt null.
- Trường giữ nguyên.
- Điều kiện version hoặc trạng thái cần thỏa mãn.

### 7.5. Version làm thay đổi kỳ vọng “có thì sửa, chưa có thì tạo”

Với optimistic locking được hỗ trợ và cấu hình đúng, một lần save có thể yêu cầu version hiện tại khớp version mong đợi.

Nếu document không còn tồn tại hoặc version đã đổi, thao tác có thể báo xung đột thay vì âm thầm tạo một document mới.

Khả năng phát hiện lỗi còn phụ thuộc các thiết lập ghi phù hợp của MongoDB. Vì vậy, không dùng một thử nghiệm save không version để kết luận hành vi của domain có version.

## 8. Spring Data JDBC: lưu aggregate theo trạng thái mới/cũ

### 8.1. Không phải JPA thu gọn

Spring Data JDBC cũng có repository và CRUD nhưng không dùng persistence context của JPA.

Một aggregate đọc về không tự trở thành entity managed với cơ chế dirty checking giống Hibernate. Việc sửa object trong bộ nhớ cần được chuyển thành thao tác lưu hoặc cập nhật phù hợp.

### 8.2. Save lựa chọn thao tác theo trạng thái

Spring Data JDBC sử dụng thông tin domain để nhận diện aggregate mới hay đã tồn tại, rồi chọn đường insert hoặc update tương ứng.

ID, version hoặc cơ chế trạng thái được hỗ trợ có thể ảnh hưởng quyết định này. Không giả định trước mỗi lần save luôn có một select kiểm tra tồn tại.

Nếu một aggregate được xem là đã tồn tại nhưng row cần cập nhật không có, store có thể báo lỗi về cập nhật không đạt kỳ vọng. Không được mặc định nó sẽ tự chuyển sang insert chỉ vì không tìm thấy row.

Nếu nghiệp vụ cần chỉ insert, Spring Data JDBC có các API chuyên biệt như thao tác insert trên JdbcAggregateTemplate. Đây là API theo store, không phải phương thức bắt buộc của CrudRepository.

### 8.3. Save aggregate có thể tác động nhiều row

Một aggregate có thể gồm root và các thành phần con được mapping. Lưu aggregate không nhất thiết chỉ phát sinh một INSERT hoặc UPDATE cho bảng root.

Cách đồng bộ phần tử con phụ thuộc mapping và implementation. Một đường cập nhật có thể cần xóa, tạo lại hoặc cập nhật các row liên quan theo chiến lược của module.

Đừng lấy một entity phẳng chỉ có vài cột làm bằng chứng rằng mọi aggregate JDBC đều có đúng một câu lệnh.

## 9. So sánh ba đường thực thi

| Câu hỏi | Spring Data JPA | Spring Data MongoDB | Spring Data JDBC |
| --- | --- | --- | --- |
| Hạ tầng chính | EntityManager và JPA provider | Hạ tầng mapping/operations MongoDB và driver | Hạ tầng mapping aggregate quan hệ và JDBC |
| Đường save điển hình | Chọn persist hoặc merge | Chọn đường insert/save theo trạng thái và mapping | Chọn insert/update aggregate theo trạng thái |
| Có managed/detached như JPA không? | Có trong vòng đời JPA | Không áp dụng nguyên mô hình JPA | Không áp dụng nguyên mô hình JPA |
| Sửa object có tự ghi nhờ dirty checking JPA không? | Có thể, khi entity managed và transaction phù hợp | Không suy như JPA | Không suy như JPA |
| ID đã có bảo đảm row/document tồn tại không? | Không | Không | Không |
| Save có luôn là patch không? | Không | Không | Không |
| Một lời gọi luôn là một lệnh vật lý không? | Không | Không | Không |

Bảng mô tả ranh giới cơ chế, không thay thế tài liệu của phiên bản và cấu hình đang dùng.

Những thay đổi về projection, truy vấn hay auditing có thể sử dụng abstraction chung của Commons. Nhưng các abstraction đó không xóa khác biệt về cách một trạng thái domain được ghi xuống từng store.

## 10. Biểu đạt rõ ý định tạo mới, cập nhật và upsert

### 10.1. Tạo mới

Một API tạo sản phẩm nên có hợp đồng rõ:

- Dữ liệu nào bắt buộc.
- Ai cấp ID.
- SKU có được trùng không.
- Khi đã có định danh hoặc khóa nghiệp vụ thì báo lỗi gì.

Nếu JPA dùng ID sinh tự động, tạo một entity mới không mang ID do client tùy ý đặt thường phù hợp với luồng tạo. Ràng buộc duy nhất trên SKU vẫn cần được thiết kế ở cơ sở dữ liệu.

Nếu store có API insert chuyên biệt, có thể dùng nó để biểu đạt ý định chỉ tạo mới trong phạm vi phù hợp. CrudRepository không bắt buộc cung cấp một method tên insert cho mọi store.

Không tạo một method `createNew` trong interface rồi mặc định Spring Data tự hiểu toàn bộ ngữ nghĩa đó. Method tùy chỉnh vẫn cần implementation hoặc cơ chế được hỗ trợ.

### 10.2. Cập nhật một đối tượng đã có

Với một service JPA đã được cấu hình và inject ProductRepository, có thể chọn cách tải domain trước rồi chỉ sửa trường được phép:

```java
import java.math.BigDecimal;
import java.util.NoSuchElementException;

import org.springframework.transaction.annotation.Transactional;

@Transactional
public Product changePrice(Long id, BigDecimal newPrice) {
    if (id == null) {
        throw new IllegalArgumentException(
                "Định danh không được null"
        );
    }

    if (newPrice == null || newPrice.signum() < 0) {
        throw new IllegalArgumentException(
                "Giá không hợp lệ"
        );
    }

    Product current = products.findById(id)
            .orElseThrow(
                    () -> new NoSuchElementException(
                            "Không tìm thấy sản phẩm"
                    )
            );

    current.changePrice(newPrice);

    return products.save(current);
}
```

Đây là phương thức bên trong service. Giả định Product có phương thức domain `changePrice` và repository quản lý đúng entity.

Cách này giữ các trường khác trên đối tượng đã tải, thay vì dựng một entity thiếu dữ liệu từ request.

Trong JPA, current đang managed có thể được dirty checking đồng bộ ngay cả khi không gọi save tường minh. Lời gọi save ở ví dụ giữ rõ việc service sử dụng hợp đồng repository và dùng đối tượng trả về.

Transaction cần được kích hoạt đúng qua Spring và transaction manager phù hợp. Nếu có transaction ngoài, ranh giới cuối cùng còn phụ thuộc transaction đó.

### 10.3. Đọc trước không tự loại bỏ cập nhật đồng thời

Một yêu cầu khác có thể thay đổi hoặc xóa sản phẩm sau khi service đã đọc.

Để tránh ghi đè không mong muốn, cân nhắc:

- Optimistic locking bằng version.
- Cập nhật có điều kiện.
- Khóa hoặc mức cô lập thích hợp khi nghiệp vụ cần.
- Xử lý trường hợp không còn bản ghi phù hợp.

Một lần findById trước save giúp xác định ý định và lấy trạng thái hiện tại tại thời điểm đọc. Nó không tự tạo bảo đảm đồng thời cho toàn bộ quy trình.

### 10.4. Upsert cần được thiết kế riêng

Nếu yêu cầu thật sự là “tạo nếu chưa có, cập nhật nếu đã có”, cần xác định:

| Quyết định | Ví dụ cần chốt |
| --- | --- |
| Khóa dùng để xác định tồn tại | Persistence ID hay SKU? |
| Trường chỉ đặt khi tạo | Thời điểm tạo, người tạo, giá trị mặc định |
| Trường thay đổi khi cập nhật | Giá, tên, trạng thái |
| Quy tắc xung đột | Ghi đè, kiểm tra version hay từ chối |
| Cơ chế thực hiện | API update/upsert của store, lệnh có điều kiện hoặc transaction |
| Kết quả cần trả | Đối tượng sau ghi, số bản ghi khớp hay phân biệt đã tạo/đã sửa |

Một chuỗi exists rồi save không tự trở thành upsert nguyên tử:

```text
A kiểm tra: chưa có SKU
B kiểm tra: chưa có SKU
A tạo SKU
B cũng thử tạo SKU
```

Ràng buộc duy nhất và cơ chế ghi phù hợp mới quyết định cách xử lý xung đột. Kiểm tra trước có thể hữu ích cho thông báo, nhưng không thay thế bảo đảm tại store.

## 11. Vì sao không nên giấu mọi khác biệt trong một base generic?

Một quy tắc như:

```text
ID null     → chắc chắn insert
ID khác null → chắc chắn update
```

bỏ qua ID tự cấp, version, Persistable, đối tượng detached và cơ chế của từng store.

Nếu đặt quy tắc này vào base repository của toàn ứng dụng, bạn có thể vô tình:

- Chọn sai đường tạo mới cho một domain.
- Làm mất kiểm tra version.
- Biến cập nhật một phần thành thay thế toàn bộ trạng thái.
- Phụ thuộc JPA merge trong một hợp đồng được gọi là dùng chung.
- Hứa khả năng upsert mà store hoặc mapping chưa cung cấp.

Một base chung có thể thống nhất chữ ký, cách xử lý không tìm thấy hoặc kiểu kết quả. Những thao tác cần hiểu sâu trạng thái và công nghệ lưu trữ nên có implementation theo store hoặc hợp đồng nghiệp vụ riêng.

Nếu đặt tên `insertOnly` hoặc `updateExisting`, hãy bảo đảm implementation thực sự thực hiện ngữ nghĩa đó. Gọi save bên trong mà không thêm cơ chế cần thiết chưa đủ chứng minh tên method là đúng.

## 12. Auditing, projection và truy vấn không thay đổi ngữ nghĩa save

### 12.1. Auditing không phải báo cáo câu lệnh vật lý

Các trường tạo/sửa có thể được điền qua hạ tầng auditing và callback/listener của store.

Có `createdAt` hoặc `lastModifiedAt` không tự chứng minh một câu INSERT hay UPDATE cụ thể đã chạy và commit. Cần xem đường ghi và thời điểm đồng bộ dữ liệu.

Cũng không dùng version như một bản thay thế cho toàn bộ lịch sử thay đổi. Version chủ yếu tham gia kiểm soát trạng thái và đồng thời theo cơ chế hỗ trợ.

### 12.2. Projection là hợp đồng đọc

Một projection chỉ có ID và giá không phải toàn bộ trạng thái Product. Dựng lại entity từ projection đó rồi save có thể bỏ mất các trường không được đọc.

Nếu nhu cầu là đổi giá, dùng domain đã được tải đủ theo thiết kế hoặc một API cập nhật trường có hợp đồng rõ. Không xem projection rút gọn như một entity đầy đủ để ghi lại.

### 12.3. Derived query và QBE không tự quyết định đường lưu

`findBySku` hoặc Query by Example giúp biểu đạt yêu cầu đọc theo thuộc tính. Save vẫn sử dụng trạng thái và metadata của đối tượng theo cơ chế store.

Việc tìm thấy một đối tượng bằng SKU không làm mọi object khác cùng SKU tự được xem là cùng persistence entity. ID và mapping vẫn phải được giữ đúng.

Tương tự, không tìm thấy qua một truy vấn đọc không chứng minh một insert sau đó chắc chắn không xung đột với yêu cầu đồng thời.

## 13. Bài thực hành: quan sát thay vì đoán từ tên method

### 13.1. Chọn một môi trường có thể kiểm soát

Chuẩn bị Product với:

- Định danh theo mapping của store.
- SKU duy nhất.
- Tên và giá.
- Version nếu bài thử kiểm soát đồng thời cần nó.

Nạp một sản phẩm có SKU KEY-001, tên Bàn phím cơ và giá 1.200.000 VND. Giữ ID và version từ kết quả thực tế, không giả định bộ sinh luôn cấp ID bằng một số cố định.

Bật log SQL hoặc command phù hợp với store trong môi trường test. Phân biệt các thao tác nạp fixture với các thao tác cần quan sát.

### 13.2. Các tình huống đối chiếu

| Tình huống | Câu hỏi cần trả lời |
| --- | --- |
| Đối tượng mới, ID theo chiến lược tạo | Hạ tầng nhận diện mới bằng dấu hiệu nào? |
| Tải sản phẩm hiện tại rồi đổi giá | Có giữ tên và SKU đúng không? |
| Dựng đối tượng có ID hiện tại nhưng thiếu trường | Null có ghi đè hay làm vi phạm ràng buộc không? |
| ID đã đặt nhưng dữ liệu chưa tồn tại | Store chọn đường nào và kết quả ra sao? |
| Hai bản trạng thái có cùng version | Khi bản thứ nhất ghi xong, bản thứ hai có bị từ chối không? |
| Lưu rồi rollback | Trạng thái database và trạng thái object còn khác nhau thế nào? |

Tình huống thiếu trường và ID không tồn tại nên thực hiện trên dữ liệu thử riêng. Mục tiêu là hiểu hợp đồng, không biến một kết quả ngẫu nhiên thành chính sách ghi của ứng dụng.

### 13.3. Quan sát riêng cho JPA

Ghi lại:

1. Quy tắc isNew đã chọn persist hay merge.
2. Instance đầu vào và instance trả về có cùng tham chiếu không.
3. Entity có đang managed trong persistence context không.
4. Khi nào xuất hiện select, insert hoặc update.
5. Flush và commit nằm ở đâu.
6. Lỗi version hoặc ràng buộc xuất hiện tại bước nào.

Không yêu cầu SQL phải dùng câu lệnh MERGE chỉ vì đường Java gọi EntityManager.merge.

### 13.4. Quan sát riêng cho MongoDB

Ghi lại:

1. ID và version khiến repository chọn đường nào.
2. Thao tác là insert, lưu document hay update có điều kiện.
3. Những trường nào được ghi lại.
4. ID chưa có trong collection dẫn đến tạo mới hay lỗi trong cấu hình đang thử.
5. Version và cấu hình ghi có phát hiện xung đột theo yêu cầu không.

So sánh thao tác lưu trạng thái với update theo một vài trường. Không dùng hai cách này như từ đồng nghĩa.

### 13.5. Quan sát riêng cho JDBC

Ghi lại:

1. Aggregate được nhận diện mới/cũ như thế nào.
2. Insert hoặc update nào được thực hiện.
3. Root và thành phần con phát sinh bao nhiêu thao tác.
4. Điều gì xảy ra nếu aggregate được xem là cũ nhưng row không tồn tại.
5. Việc chỉ sửa object trong bộ nhớ có tạo ghi khi không gọi thao tác lưu không.

Đối chiếu với JPA để nhận ra vai trò khác nhau của persistence context và việc lưu aggregate tường minh.

### 13.6. Kịch bản optimistic locking phải có hai trạng thái độc lập

Để kiểm tra xung đột:

```text
Lần đọc A: version = v
Lần đọc B: version = v

A sửa giá và ghi thành công
    → version trong store thay đổi theo cơ chế hỗ trợ

B ghi với version cũ
    → kỳ vọng phát hiện xung đột nếu cấu hình đúng
```

Hai lần đọc phải tạo hai trạng thái độc lập, chẳng hạn từ hai transaction/context khác nhau. Trong cùng persistence context JPA, hai lần findById có thể trả về chính một instance nên không mô phỏng đúng hai người sửa đồng thời.

Sau lỗi, xác minh trạng thái bằng một lần đọc hợp lệ ở ranh giới phù hợp. Đừng tiếp tục dùng một transaction đã lỗi để kết luận kết quả cuối cùng.

## 14. Những kết luận sai cần sửa

| Kết luận sai | Cách diễn đạt đúng hơn |
| --- | --- |
| Save luôn chạy UPDATE | Save là hợp đồng lưu; đường ghi phụ thuộc trạng thái và store |
| ID khác null nghĩa là bản ghi tồn tại | ID là một dấu hiệu metadata, cần đặt trong cơ chế phát hiện trạng thái |
| JPA merge dùng SQL MERGE | Merge là thao tác vòng đời JPA, provider quyết định SQL |
| Gọi save làm object detached thành managed | Phải dùng instance do merge/save trả về theo đường thực thi |
| Save object thiếu trường sẽ giữ các trường cũ | Không mặc định; cần hợp đồng patch hoặc tải/sửa trạng thái phù hợp |
| Có ID là đã commit | ID có thể được cấp trước commit và còn trong bộ nhớ sau rollback |
| Cùng CrudRepository nên mọi store ghi giống nhau | Hợp đồng chung không đồng nhất cơ chế lưu trữ |
| Đã kiểm tra tồn tại thì không có race condition | Đọc và ghi vẫn có khoảng thời gian bị thay đổi nếu thiếu bảo đảm tương ứng |

## 15. Điều cần mang theo khi thiết kế repository

Bắt đầu bằng ý định nghiệp vụ: tạo mới, cập nhật đối tượng hiện có, sửa một phần hay upsert. Sau đó xác định metadata và trạng thái domain, chọn API của store phù hợp, sử dụng đối tượng trả về và kiểm tra ranh giới transaction.

Spring Data Commons giúp ứng dụng dùng một ngôn ngữ repository và CRUD nhất quán. Sự nhất quán đó nằm ở hợp đồng; insert, update, merge, thay thế document, dirty checking và lưu aggregate vẫn phải được hiểu theo công nghệ thực hiện.

