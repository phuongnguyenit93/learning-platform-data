# `save` và ý nghĩa kiểu trả về `<S extends T>`

Trong Spring Data, một lời gọi `repository.save(entity)` nhìn giống thao tác CRUD đơn giản. Tuy nhiên, chữ ký của nó chứa một quyết định quan trọng về kiểu dữ liệu:

```java
<S extends T> S save(S entity);
```

Phương thức không chỉ nhận và trả lại kiểu miền `T` của repository. Nó khai báo một tham số kiểu riêng `S`, giới hạn `S` nằm trong họ kiểu của `T`, rồi liên kết kiểu đầu vào với kiểu kết quả. Hiểu liên kết này giúp đọc API chính xác, tránh ép kiểu không cần thiết và sử dụng đúng đối tượng sau khi lưu.

Bài này thuộc chương **Hợp đồng CRUD** của Spring Data Commons (`SPRING_DATA_COMMONS`). Ta sẽ phân biệt ba vấn đề thường bị trộn lẫn: **kiểu tĩnh của kết quả, instance thực tế được trả về và cơ chế lưu của từng module**. Các abstraction Commons thống nhất nhiều phần của hợp đồng, nhưng việc nhận diện đối tượng mới, mapping, auditing, kiểm soát phiên bản và giao dịch vẫn phụ thuộc khả năng cùng cấu hình của store.

Các đoạn mã về generics là ví dụ đọc kiểu Java, không phải một ứng dụng persistence hoàn chỉnh. Khi thực thi, vẫn cần module Spring Data, mô hình được mapping hợp lệ, dependency tương thích và môi trường lưu trữ phù hợp.

## 1. Đọc chữ ký từ ngoài vào trong

Một phần hợp đồng repository có hình dạng:

```java
public interface CrudRepository<T, ID> extends Repository<T, ID> {
    <S extends T> S save(S entity);
}
```

Đây là đoạn trích để đọc chữ ký, không phải toàn bộ mã nguồn của interface.

| Thành phần | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| `T` | Tham số kiểu của repository | Kiểu miền mà repository quản lý. |
| `ID` | Tham số kiểu của repository | Kiểu định danh dùng trong các thao tác như `findById`. |
| `<S extends T>` | Tham số kiểu của phương thức `save` | Mỗi lời gọi chọn một kiểu `S` phù hợp với giới hạn trên `T`. |
| `S entity` | Tham số của phương thức | Đầu vào phải có kiểu phù hợp với `S`. |
| `S` trước tên `save` | Kiểu trả về | Kết quả có cùng tham số kiểu `S` được xác định cho lời gọi. |

Nếu khai báo:

```java
interface DocumentRepository extends CrudRepository<Document, Long> {
}
```

thì `T` đã là `Document`, `ID` đã là `Long`. Chữ ký tương ứng của thao tác lưu có thể được đọc là:

```java
<S extends Document> S save(S entity);
```

`S` không phải một field của entity và không liên quan trực tiếp đến ID. Nó là tên tham số kiểu Java; tên có thể khác mà ý nghĩa vẫn giữ nguyên.

### 1.1. `extends` ở đây là giới hạn trên

`S extends T` cho phép `S` là chính `T` hoặc một kiểu con hợp lệ của `T`. Không nên đọc thành “chỉ nhận lớp con, không nhận `T`”.

Trong khai báo giới hạn của generics, `extends` cũng được dùng khi giới hạn là interface. Nó không có nghĩa mọi trường hợp đều là quan hệ kế thừa giữa hai lớp cụ thể.

### 1.2. Kiểu được chọn theo từng lời gọi

Một repository quản lý `Document` có thể được dùng ở nhiều lời gọi với những kiểu `S` khác nhau, nếu mô hình thực tế và module cho phép lưu chúng:

```text
Lời gọi 1: S = Invoice
Lời gọi 2: S = Report
Lời gọi 3: S = Document
```

Điều này không thay đổi kiểu `T` đã khai báo trên repository. Repository vẫn quản lý `Document`; phương thức bảo toàn thông tin kiểu thích hợp tại từng điểm gọi.

## 2. Vì sao không chỉ viết `T save(T entity)`?

Giả sử có mô hình tối giản để đọc generics:

```java
class Document {
}

class Invoice extends Document {
}

class Report extends Document {
}
```

Những lớp rỗng này chỉ minh họa quan hệ kiểu. Chúng chưa có định danh hay mapping để chạy với một store.

Nếu phương thức có chữ ký `T save(T entity)` trên repository của `Document`, kiểu trả về chỉ được mô tả là `Document`:

```java
// Giả sử API này chỉ khai báo: Document save(Document entity).
Document saved = simplifiedRepository.save(new Invoice());
```

Dù truyền một `Invoice`, hợp đồng này không giữ kiểu `Invoice` ở kết quả. Muốn gán kết quả cho biến `Invoice`, người gọi có thể phải ép kiểu hoặc thiết kế lại API.

Với chữ ký của `CrudRepository`:

```java
Invoice input = new Invoice();
Invoice saved = documents.save(input);
```

Java có thể suy luận `S` là `Invoice`. Vì tham số và kết quả cùng dùng `S`, không cần một cast để lấy kiểu trả về mong muốn.

Có thể hình dung:

```text
T = Document
    └── S = Invoice
          ├── tham số: Invoice
          └── kết quả: Invoice
```

Đây là lợi ích của một **generic method**. Nó không phải bằng chứng rằng repository đã đổi thành `CrudRepository<Invoice, Long>`.

### 2.1. `S = T` vẫn là trường hợp bình thường

Nếu repository quản lý trực tiếp một loại `LearningTask`, không có phân cấp lớp cần quan tâm:

```java
interface TaskRepository extends CrudRepository<LearningTask, Long> {
}

LearningTask saved = tasks.save(task);
```

Ở lời gọi này, `S` có thể là `LearningTask`, bằng với `T`. Không cần tạo một lớp con chỉ để “sử dụng đúng” chữ ký generic.

### 2.2. Kiểu không thuộc họ `T` vẫn bị loại

Với repository quản lý `Document`, lời gọi sau không hợp lệ về kiểu:

```java
// Không hợp lệ: String không thuộc họ Document.
documents.save("Nội dung bất kỳ");
```

`<S extends T>` mở khả năng bảo toàn kiểu con, không biến repository thành nơi lưu mọi đối tượng Java.

## 3. Kiểu tĩnh quyết định thông tin nào được bảo toàn

Điểm dễ nhầm là Java suy luận từ các kiểu tại vị trí gọi, không tự khôi phục mọi thông tin kiểu đã bị làm rộng trước đó.

```java
Invoice invoice = new Invoice();
Invoice first = documents.save(invoice);

Document widened = invoice;
Document second = documents.save(widened);
```

`widened` đang tham chiếu đến một `Invoice`, nhưng kiểu khai báo của biến là `Document`. Tại lời gọi thứ hai, hợp đồng có thể được sử dụng với `S` là `Document`.

Không thể chỉ dựa vào đối tượng runtime để viết:

```java
Document widened = new Invoice();

// Không hợp lệ: tham số có kiểu Document, không đủ để bảo đảm kết quả Invoice.
Invoice saved = documents.save(widened);
```

Compiler không chấp nhận việc suy luận rằng mọi `Document` truyền vào đều là `Invoice`.

### 3.1. `var` không lấy lại kiểu đã bị làm rộng

```java
Invoice invoice = new Invoice();
var first = documents.save(invoice);
// first có kiểu tĩnh Invoice.

Document document = invoice;
var second = documents.save(document);
// second có kiểu tĩnh Document.
```

`var` yêu cầu compiler suy luận kiểu biến từ biểu thức. Nó không biến việc suy luận đó thành một phép kiểm tra lớp runtime.

### 3.2. Có thể chỉ định tham số kiểu, nhưng không chữa được đầu vào sai kiểu

Cú pháp Java cho phép:

```java
Invoice saved = documents.<Invoice>save(invoice);
```

Thường không cần viết rõ vì compiler đã suy luận được. Nếu đầu vào chỉ có kiểu `Document`, chỉ định `<Invoice>` không làm nó tự trở thành `Invoice`:

```java
Document document = new Invoice();

// Không hợp lệ: document không có kiểu tĩnh phù hợp với tham số Invoice.
Invoice saved = documents.<Invoice>save(document);
```

Cách giải quyết thông thường là giữ kiểu thích hợp ở biên API khi thật sự cần nó, thay vì thêm cast chỉ để che một thiết kế đã làm mất thông tin kiểu.

### 3.3. Generics của repository không tự có covariance

Trong Java, `CrudRepository<Invoice, Long>` không tự là kiểu con của `CrudRepository<Document, Long>` chỉ vì `Invoice` kế thừa `Document`.

Khả năng nhận `Invoice` và trả `Invoice` của `save` đến từ tham số kiểu cấp phương thức `<S extends T>`. Không nên dùng nó để suy ra quy tắc thay thế giữa mọi kiểu repository đã tham số hóa.

## 4. Giữ liên kết kiểu khi viết phương thức trung gian

Một phương thức bọc có thể vô tình làm mất lợi ích mà API gốc cung cấp:

```java
static Document saveDocument(
        CrudRepository<Document, Long> repository,
        Document document) {
    return repository.save(document);
}
```

Với chữ ký này, người gọi chỉ nhận `Document`, dù truyền `Invoice`. Framework không làm mất kiểu; chính hợp đồng của phương thức trung gian đã làm rộng đầu vào và đầu ra.

Nếu mục tiêu của helper là giữ kiểu con trong họ `Document`, có thể viết:

```java
static <S extends Document> S saveDocument(
        CrudRepository<Document, Long> repository,
        S document) {
    return repository.save(document);
}
```

Khi đó:

```java
Invoice saved = saveDocument(documents, new Invoice());
```

Không cần tạo helper như vậy chỉ để bọc một lời gọi. Ví dụ này cho thấy cần bảo toàn liên kết kiểu khi có lý do thật để xây dựng một lớp API trung gian.

Một service nghiệp vụ cũng có thể chủ đích trả về DTO thay vì entity. Điều đó hoàn toàn khác với việc vô tình làm mất kiểu: service đang định nghĩa hợp đồng kết quả riêng theo nhu cầu của ca sử dụng.

## 5. Kiểu trả về không đồng nghĩa cùng instance

Sau khi hiểu `S`, cần tách câu hỏi về kiểu khỏi câu hỏi về danh tính đối tượng Java.

```java
LearningTask input = new LearningTask("Học hợp đồng CRUD");
LearningTask saved = tasks.save(input);
```

Hợp đồng cho biết `saved` có kiểu phù hợp với lời gọi. Nó không cho phép mặc định:

```java
saved == input
```

luôn là `true`.

`==` so sánh hai tham chiếu có trỏ đến cùng một đối tượng Java hay không. Một store có thể cập nhật đối tượng truyền vào; một store hoặc mô hình khác có thể trả về một instance khác thể hiện trạng thái sau lưu.

Ví dụ trạng thái cần sử dụng sau khi lưu có thể gồm:

- ID được cấp hoặc được xử lý theo chiến lược của store.
- Giá trị phiên bản khi cơ chế kiểm soát đồng thời được hỗ trợ và bật đúng.
- Dữ liệu auditing được gán trong vòng đời lưu phù hợp.
- Trạng thái đã đi qua cơ chế mapping hoặc callback của module.

Những khả năng này phụ thuộc mô hình, module và cấu hình. Không phải mọi lời gọi `save` đều tự phát sinh tất cả các giá trị trên.

### 5.1. Quy tắc sử dụng: tiếp tục với kết quả trả về

Cách viết rõ ràng:

```java
LearningTask saved = tasks.save(input);
Long id = saved.getId();
```

Cách dễ phụ thuộc vào hành vi riêng của triển khai:

```java
tasks.save(input);
Long id = input.getId();
```

Cách thứ hai có thể hoạt động trong một cấu hình, nhưng không nên được coi là hệ quả của chữ ký Commons. Khi cần dữ liệu sau lưu, sử dụng kết quả trả về giúp mã không phụ thuộc vào việc instance đầu vào có được thay đổi trực tiếp hay không.

Nếu cần xác nhận trạng thái đã thực sự được lưu đúng, một phép đọc lại trong bối cảnh kiểm thử thích hợp còn cung cấp bằng chứng khác với chỉ quan sát đối tượng trả về.

### 5.2. Mô hình bất biến làm khác biệt này dễ thấy hơn

Với mô hình bất biến, đối tượng không nhất thiết có setter để thay ID hoặc version tại chỗ. Module có thể cần dựng instance mới mang trạng thái sau lưu nếu hỗ trợ kiểu mô hình đó.

```text
Trước lưu: instance A, id chưa có
Sau lưu:   instance B, id đã được cấp

Kiểu tĩnh của cả hai có thể giống nhau.
A và B không bắt buộc là cùng một tham chiếu.
```

`<S extends T>` không cản việc trả instance mới. Nó yêu cầu kết quả phù hợp với kiểu `S` của lời gọi, không yêu cầu địa chỉ đối tượng Java giữ nguyên.

## 6. JPA minh họa vì sao kết quả `save` quan trọng

Spring Data JPA thường chọn đường `persist` cho entity được nhận diện là mới và đường `merge` cho entity không được nhận diện là mới. Đây là cơ chế của module JPA, không phải định nghĩa nội bộ bắt buộc của mọi repository Commons.

Đặc biệt, JPA `merge` đưa trạng thái vào một entity được quản lý và trả về tham chiếu đến entity được quản lý tương ứng. Đối tượng đầu vào đang detached không tự trở thành managed chỉ vì được truyền vào `merge`.

```java
Order detached = obtainDetachedOrder();
Order saved = orders.save(detached);
```

Trong trường hợp đó, dùng `saved` có ý nghĩa khác với tiếp tục mặc định `detached` là instance đang được persistence context quản lý.

Cần thêm một giới hạn quan trọng: entity được quản lý trong một persistence context không có nghĩa nó tiếp tục được quản lý sau mọi ranh giới giao dịch hoặc khi context đã đóng. Giá trị trả về của `save` không cấp một trạng thái “managed vĩnh viễn”.

Trong một giao dịch JPA bao ngoài, entity đang managed có thể được đồng bộ bằng dirty checking. Nhưng một repository ở store khác không mặc định có cơ chế tương đương. Khi học hợp đồng Commons, hãy giữ riêng:

```text
Kiểu trả về:             Java generics và hợp đồng phương thức
Instance trả về:         kết quả thực tế sau thao tác lưu
Trạng thái persistence:  cơ chế và vòng đời của module/store
```

## 7. Generics không quyết định `INSERT`, `UPDATE` hay trạng thái mới

`S` là kiểu Java, không phải cờ cho biết entity đã tồn tại trong database hay chưa. Cùng một kiểu `LearningTask` có thể được truyền vào khi tạo mới hoặc khi lưu một thay đổi.

```java
LearningTask created = tasks.save(newTask);
LearningTask updated = tasks.save(changedTask);
```

Cả hai lời gọi đều có thể dùng `S = LearningTask`, trong khi module xử lý trạng thái persistence khác nhau.

### 7.1. Nhận diện đối tượng mới là một cơ chế khác

Module có thể xem xét ID, thuộc tính phiên bản hoặc cơ chế như `Persistable.isNew()` để quyết định đường lưu. Quy tắc cụ thể cần được hiểu theo module và phiên bản đang sử dụng.

Không dùng hai suy luận tuyệt đối sau:

```text
ID khác null  => chắc chắn đối tượng đã có trong database.
ID bằng null => mọi store đều có thể tự sinh ID phù hợp.
```

Đối tượng mới có thể đã được ứng dụng cấp ID trước. Ngược lại, một mô hình có ID rỗng có thể không có chiến lược tự cấp ID hợp lệ với store. Kiểu `ID` trên repository chỉ mô tả kiểu dữ liệu định danh, không tự cấu hình cơ chế cấp định danh.

Nếu dùng `Persistable`, giá trị `isNew()` trở thành một phần trách nhiệm của mô hình và vòng đời lưu theo cơ chế hỗ trợ. Không trả về `true` mãi chỉ để buộc lưu được một lần rồi bỏ qua hệ quả ở các lần lưu tiếp theo.

### 7.2. `save` không phải cách diễn đạt một phép PATCH phổ quát

Một lỗi thiết kế là tạo đối tượng chỉ có ID và một thuộc tính rồi gọi `save`, với giả định mọi thuộc tính còn lại sẽ được giữ nguyên:

```java
// Ý định: chỉ đổi title.
// Rủi ro: đối tượng này có thể thiếu trạng thái cần thiết cho đường lưu.
LearningTask partial = createPartialTask(id, newTitle);
tasks.save(partial);
```

Commons không định nghĩa `save` là “bỏ qua mọi giá trị null rồi cập nhật các trường còn lại”. Hành vi lưu, merge, thay thế trạng thái và xử lý thuộc tính tùy store và mapping.

Đường cập nhật thường rõ ràng hơn khi đọc đối tượng, áp dụng hành vi được phép rồi lưu kết quả:

```java
LearningTask task = tasks.findById(id)
    .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy công việc"));
task.rename(newTitle);
LearningTask saved = tasks.save(task);
```

Đây là đoạn điều phối minh họa; `rename` cần được mô hình hiện thực. Trong ứng dụng thật, ranh giới giao dịch và kiểm soát đồng thời phải được chọn phù hợp. Chuỗi đọc rồi lưu tự nó chưa loại được các cuộc đua cập nhật.

Nếu cần một phép cập nhật có điều kiện hoặc cập nhật một phần ở mức database, dùng khả năng tương ứng của module hay triển khai tùy biến, rồi kiểm tra tác động tới callback, version và auditing.

### 7.3. Chữ ký không xác định chính sách tạo mới hay upsert

Tên `save` và kiểu trả về không cho biết mọi store luôn thực hiện cùng một chính sách “chưa có thì thêm, có rồi thì sửa”. Chẳng hạn một module có thể đi qua cơ chế persistence của JPA, một module document có thể có cách lưu khác.

Nếu nghiệp vụ yêu cầu “chỉ tạo khi chưa tồn tại” hoặc “chỉ cập nhật đúng phiên bản hiện tại”, hãy thể hiện và bảo vệ điều kiện ấy bằng khả năng thích hợp. Không suy ra điều kiện từ tên `save`.

Một lần `existsById` trước `save` cũng không tự làm chuỗi thao tác trở thành nguyên tử: trạng thái có thể đổi giữa hai lần truy cập.

## 8. Kiểu con được Java chấp nhận vẫn cần mapping hợp lệ

Ví dụ generic cho phép:

```java
Invoice saved = documents.save(new Invoice());
```

Nhưng việc compiler chấp nhận chỉ xác nhận quan hệ kiểu Java. Để lưu được, còn cần module biết cách xử lý `Invoice`:

- Có mapping cho kiểu miền hoặc chiến lược phân cấp phù hợp không?
- ID và cách cấp ID có hợp lệ không?
- Store biểu diễn dữ liệu của kiểu con như thế nào?
- Khi đọc lại qua repository của kiểu gốc, dữ liệu được dựng thành kiểu nào?
- Những converter hoặc callback có phù hợp với mô hình này không?

JPA có các cơ chế mapping kế thừa riêng. Module document có cách nhận diện kiểu và dựng đối tượng của nó. Không nên mang cấu hình của một bên sang bên kia chỉ vì cả hai dùng `CrudRepository`.

### 8.1. Kiểu `S` không phải lời hứa về `getClass()`

Kiểu trả về phù hợp với `S` không đòi hỏi kết quả luôn có đúng một lớp runtime cụ thể giống hệt đầu vào. Persistence provider có thể dùng proxy hoặc một dạng đối tượng được hỗ trợ bởi mô hình.

Do đó, khi kiểm tra kết quả, ưu tiên các thuộc tính và hành vi thuộc hợp đồng thay vì khẳng định:

```java
saved.getClass() == input.getClass()
```

luôn phải đúng với mọi store và cấu hình.

Nếu gọi bằng một biến có kiểu tĩnh `Document`, `S` có thể là `Document`; chữ ký đó không tự cung cấp một bảo đảm đặc biệt rằng người gọi có thể ép kết quả thành một kiểu con bất kỳ.

## 9. Đối tượng trả về không đồng nghĩa đã commit

Một lời gọi `save` trả về bình thường chưa đủ để khẳng định dữ liệu đã được commit và bền vững ở mọi bối cảnh.

Cần tách các thời điểm:

| Thời điểm | Ý nghĩa |
| --- | --- |
| Lời gọi `save` trả về | Người gọi có kết quả của thao tác theo hợp đồng và triển khai hiện tại. |
| Đồng bộ thay đổi xuống database | Có thể liên quan đến flush trong JPA hoặc cơ chế ghi của module khác. |
| Kết thúc giao dịch thành công | Thay đổi được commit theo giao dịch và khả năng store đang dùng. |
| Đọc lại ở một bối cảnh khác | Kiểm tra được trạng thái có thể quan sát trong bối cảnh đó, theo mức cô lập và cấu hình liên quan. |

Các thời điểm có thể gần nhau hoặc nằm ở những ranh giới khác nhau. Với JPA trong giao dịch bao ngoài, SQL hoặc lỗi ràng buộc có thể xuất hiện muộn hơn lời gọi `save`.

Ví dụ service:

```java
@Transactional
public Order confirm(Long id) {
    Order order = orders.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy đơn"));
    order.confirm();
    return orders.save(order);
}
```

Giả sử service được gọi qua cơ chế giao dịch Spring phù hợp, việc kết thúc giao dịch được điều phối ở ranh giới proxy. Lệnh `return` trong thân phương thức không làm cho `save` trở thành một cam kết commit độc lập ngay tại dòng đó; lỗi vẫn có thể xuất hiện khi giao dịch được hoàn tất trước khi kết quả được trả tới bên gọi ngoài.

Vì vậy, một khối bắt lỗi chỉ bao quanh `save` bên trong service không chắc bao phủ mọi lỗi xảy ra lúc kết thúc giao dịch.

`CrudRepository` cũng không khai báo một lời hứa chung về flush. Các phương thức như `saveAndFlush` thuộc API chuyên biệt, chẳng hạn module JPA; flush vẫn không đồng nghĩa commit.

## 10. Lỗi đầu vào, xung đột và trách nhiệm của người gọi

### 10.1. Không dùng `null` để biểu diễn không có entity

Tham số của `save` phải là entity hợp lệ, không được null. Không viết:

```java
// Không hợp lệ theo hợp đồng đầu vào.
tasks.save(null);
```

Nếu không có đối tượng để lưu, hãy xử lý tình huống ấy trước khi gọi repository. `save` không phải phương thức nhận một `Optional` rồi tự quyết định bỏ qua.

Kết quả thành công của `save` là đối tượng đã lưu, không phải `Optional<S>`. Ngược lại, `findById` dùng `Optional<T>` vì tìm theo định danh có thể không có kết quả.

Hai chữ ký trả lời hai câu hỏi khác nhau:

```java
<S extends T> S save(S entity);  // lưu một đối tượng đã cung cấp
Optional<T> findById(ID id);    // tìm một đối tượng có thể không tồn tại
```

### 10.2. Kiểu Java đúng chưa đủ bảo đảm dữ liệu hợp lệ

Một entity có kiểu phù hợp vẫn có thể vi phạm ràng buộc database, mapping, quy tắc nghiệp vụ hoặc giới hạn kiểu dữ liệu.

| Tình huống | Hướng xử lý |
| --- | --- |
| Tham số null | Kiểm soát đầu vào trước repository. |
| Thiếu mapping hoặc converter | Sửa mô hình và cấu hình module tương ứng. |
| Vi phạm khóa duy nhất hoặc ràng buộc khác | Xác định quy tắc dữ liệu và xử lý lỗi theo ngữ cảnh nghiệp vụ. |
| Version không còn khớp | Xử lý xung đột đồng thời theo chính sách ứng dụng và khả năng store. |
| Lỗi khi flush hoặc commit | Xem cả ranh giới giao dịch, không chỉ dòng `save`. |

Không có một danh sách ngoại lệ duy nhất bao phủ mọi đường lưu của tất cả module. Commons cung cấp những hợp đồng và hệ thống ngoại lệ liên quan, còn lỗi cụ thể có thể phát sinh từ module, driver hoặc cơ chế persistence.

### 10.3. Optimistic locking cần hỗ trợ thật

Khi store hỗ trợ optimistic locking và mô hình được cấu hình đúng, version có thể tham gia điều kiện cập nhật. Nếu trạng thái không còn khớp, thao tác có thể thất bại bằng lỗi như `OptimisticLockingFailureException` hoặc kiểu lỗi tương ứng trong đường thực thi.

Việc `S` giữ nguyên kiểu không có nghĩa save luôn thành công trước xung đột. Không bắt mọi lỗi version rồi lặp lại cùng entity cũ một cách mù quáng. Có thể cần đọc lại trạng thái, tính lại quyết định nghiệp vụ hoặc thông báo xung đột theo yêu cầu cụ thể.

Auditing ghi nhận người hoặc thời điểm thao tác cũng không tự thay thế optimistic locking. Metadata lịch sử và kiểm soát cập nhật đồng thời có trách nhiệm khác nhau.

## 11. Liên hệ với `saveAll` và các kiểu repository khác

Hợp đồng của `CrudRepository` mở rộng ý tưởng giữ kiểu sang tập phần tử:

```java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
```

Nếu đầu vào được khai báo là tập `Invoice`, kết quả có thể giữ kiểu phần tử tương ứng:

```java
List<Invoice> input = List.of(new Invoice(), new Invoice());
Iterable<Invoice> saved = documents.saveAll(input);
```

Nếu đầu vào đã được làm rộng thành tập `Document` chứa nhiều loại:

```java
List<Document> mixed = List.of(new Invoice(), new Report());
Iterable<Document> saved = documents.saveAll(mixed);
```

Hợp đồng không cung cấp một kiểu tĩnh khác nhau cho từng vị trí trong một collection Java đồng nhất về kiểu phần tử khai báo.

### 11.1. Không nhầm `Iterable` với `List`

Với `CrudRepository`, không gán trực tiếp kết quả `saveAll` cho `List<S>` chỉ vì một triển khai cụ thể có thể trả về một đối tượng implement `List`:

```java
// Không dựa vào giả định này khi hợp đồng trả Iterable<Invoice>.
// List<Invoice> saved = documents.saveAll(input);
```

`ListCrudRepository` là biến thể cung cấp `List` ở các thao tác tập hợp tương ứng. Kiểu container của kết quả và kiểu phần tử `S` là hai vấn đề riêng.

Không sửa bằng cast từ `Iterable` sang `List` để phụ thuộc vào chi tiết triển khai. Chọn hợp đồng phù hợp hoặc chuyển kết quả sang collection mong muốn một cách rõ ràng.

### 11.2. `saveAll` không tự là bulk operation nguyên tử

Hợp đồng lưu nhiều phần tử không tự bảo đảm:

- Chỉ có một câu SQL hoặc một yêu cầu mạng.
- JDBC batching được bật.
- Mọi store đều lưu cả tập trong một giao dịch duy nhất.
- Callback hoặc auditing có cùng hành vi với một API bulk đặc thù khác.

Khi cần ghép kết quả với đầu vào, không mặc định hợp đồng dùng chung đã bảo đảm mọi chi tiết về thứ tự mà ứng dụng muốn dựa vào. Đối chiếu tài liệu của module hoặc dùng định danh phù hợp để liên kết khi cần.

### 11.3. Reactive repository có thêm lớp kết quả

Một hợp đồng reactive tương ứng có thể có hình dạng:

```java
<S extends T> Mono<S> save(S entity);
```

Liên kết kiểu `S` vẫn hiện diện, nhưng kết quả nằm trong publisher. Nhận được `Mono` chưa đồng nghĩa thao tác đã được thực thi và hoàn tất; cần hiểu subscription cùng vòng đời reactive của module.

Không biến một lời gọi repository đồng bộ thành truy cập không chặn chỉ bằng cách bọc kết quả trong `Mono`. Chọn module và driver reactive có hỗ trợ khi dùng hợp đồng reactive.

## 12. Quan sát đúng khi thực hành và kiểm thử

Để kiểm tra một đường lưu cụ thể, cần chọn store thực thi được mô hình và đặt kỳ vọng theo hợp đồng phù hợp.

### 12.1. Kiểm tra điều gì có giá trị?

- Lấy đối tượng từ kết quả `save` và kiểm tra những thuộc tính sau lưu mà mô hình thực sự yêu cầu.
- Đọc lại để kiểm tra dữ liệu đã được mapping đúng, thay vì chỉ nhìn instance đầu vào.
- Với mô hình bất biến được store hỗ trợ, xác nhận dữ liệu sau lưu có trên kết quả trả về.
- Với version hoặc auditing, bật cấu hình cần thiết và kiểm tra bằng nguồn dữ liệu xác định.
- Với giao dịch, quan sát trạng thái sau commit hoặc rollback ở ranh giới thích hợp.

Một test chỉ gọi `save` trên mock rồi so sánh với giá trị mock đã trả sẵn không chứng minh được cơ chế cấp ID, mapping hoặc nhận diện entity mới của store.

### 12.2. Tránh kiểm tra nhầm instance thay vì persistence

Trong JPA, persistence context có thể giữ entity vừa tạo hoặc sửa. Khi mục tiêu là kiểm tra trạng thái đã đi qua database, cần thiết kế phép đọc lại phù hợp, chẳng hạn đồng bộ và tách entity khỏi context trước khi đọc trong một test được cấu hình đúng.

Điều đó không biến `flush` thành commit. Nếu mục tiêu là xác nhận giao dịch service, không dùng một giao dịch test bao ngoài để vô tình cung cấp ranh giới mà mã service đang thiếu.

Các kỹ thuật này phụ thuộc JPA. Với MongoDB, JDBC hoặc store khác, chọn cách xác minh theo cơ chế tương ứng thay vì sao chép thao tác với `EntityManager`.

### 12.3. Phân biệt bốn câu hỏi trong kết quả kiểm tra

| Câu hỏi | Bằng chứng phù hợp |
| --- | --- |
| Compiler có giữ kiểu `Invoice` không? | Chữ ký và mã Java sử dụng đúng generics. |
| `save` trả về dữ liệu sau lưu nào? | Quan sát kết quả thật của module với mô hình và cấu hình đã chọn. |
| Dữ liệu có được ghi đúng không? | Đọc lại qua đường lưu trữ phù hợp, tránh chỉ nhìn trạng thái bộ nhớ. |
| Ca sử dụng có commit hoặc rollback đúng không? | Kiểm tra ranh giới giao dịch và trạng thái có thể quan sát sau ranh giới ấy. |

Không dùng một bằng chứng ở hàng đầu để kết luận thay cho cả ba hàng còn lại.

## 13. Những lỗi thường gặp khi đọc và sử dụng `save`

| Cách hiểu hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| `<S extends T>` chỉ nhận lớp con của `T` | Bỏ qua trường hợp `S` chính là `T`. | Đọc đây là giới hạn trên. |
| Kiểu runtime là `Invoice` nên mọi biến đều lấy lại được kiểu đó | Bỏ qua kiểu tĩnh đã khai báo. | Giữ kiểu phù hợp tại biên API hoặc chấp nhận hợp đồng rộng hơn. |
| Gọi `save` rồi luôn dùng instance cũ | Phụ thuộc việc triển khai thay đổi đầu vào tại chỗ. | Dùng đối tượng trả về khi cần trạng thái sau lưu. |
| `saved == input` phải luôn đúng | Nhầm kiểu trả về với danh tính tham chiếu. | Kiểm tra dữ liệu và hành vi cần thiết, không giả định cùng instance. |
| ID khác null nghĩa là entity chắc chắn tồn tại | Nhầm định danh đã cấp với trạng thái persistence. | Hiểu cơ chế nhận diện mới của module và mô hình. |
| Compiler nhận kiểu con thì store chắc chắn lưu được | Nhầm kiểm tra kiểu với hỗ trợ mapping. | Cấu hình và kiểm tra khả năng của store. |
| `save` tương đương cập nhật các trường khác null | Gán cho API một ngữ nghĩa PATCH không có trong hợp đồng chung. | Thiết kế luồng cập nhật hoặc dùng thao tác chuyên biệt phù hợp. |
| `save` trả về là đã commit | Nhầm thời điểm lời gọi kết thúc với giao dịch hoàn tất. | Xác định ranh giới giao dịch, flush và commit. |
| Cast kết quả để chữa mất kiểu | Có thể che hợp đồng trung gian không phù hợp. | Xem lại chữ ký helper hoặc service trước. |
| Dùng raw `CrudRepository` cho tiện | Làm suy yếu kiểm tra kiểu và phát sinh unchecked warning. | Giữ đầy đủ tham số kiểu repository. |

## 14. Bài tập đọc hợp đồng

### Bài 1: suy luận kiểu ở từng lời gọi

Giả sử `Invoice` và `Report` đều kế thừa `Document`, còn `documents` có kiểu `CrudRepository<Document, Long>`:

```java
Invoice invoice = new Invoice();
Document document = invoice;

var a = documents.save(invoice);
var b = documents.save(document);
Report c = documents.save(new Report());
```

**Gợi ý:** `a` có kiểu tĩnh `Invoice`, `b` có kiểu tĩnh `Document`, còn `c` phù hợp với lời gọi dùng `S = Report`. Việc `document` đang tham chiếu đến một `Invoice` không đổi kiểu tĩnh của nó.

### Bài 2: tìm giả định về instance

Một đoạn mã gọi `notes.save(note)` rồi trả `note.getId()` mà không dùng kết quả `save`. Rủi ro nằm ở đâu?

**Gợi ý:** Mã giả định ID đã được cập nhật trực tiếp trên đầu vào. Dùng kết quả trả về và kiểm tra chiến lược cấp ID của mô hình/store.

### Bài 3: kiểu đúng nhưng lưu thất bại

`Invoice saved = documents.save(invoice)` biên dịch thành công nhưng module báo kiểu chưa được mapping. Có mâu thuẫn với `<S extends T>` không?

**Gợi ý:** Không. Generics xác nhận quan hệ kiểu Java; mapping và khả năng persistence là điều kiện khác.

### Bài 4: test dùng `save` đã đủ chưa?

Một test lưu entity trong giao dịch đang mở và thấy ID không null. Có thể kết luận giao dịch đã commit thành công không?

**Gợi ý:** Chưa. ID có thể được cấp trước commit. Cần kiểm tra mục tiêu giao dịch ở ranh giới thích hợp và xử lý khả năng lỗi lúc hoàn tất.

### Bài 5: bảo toàn kiểu qua helper

Một helper nhận và trả `Document`, nhưng người gọi muốn truyền `Invoice` rồi nhận kết quả có kiểu `Invoice`. Nên bắt đầu sửa ở đâu?

**Gợi ý:** Xem helper có thật sự cần bảo toàn kiểu con không. Nếu có, liên kết đầu vào và đầu ra bằng tham số kiểu cấp phương thức thay vì thêm cast ở mọi nơi gọi.

Khi đọc `save`, hãy giữ ba ý đi cùng nhau: **`S` liên kết kiểu đầu vào với kết quả; kết quả trả về là đối tượng cần dùng cho trạng thái sau lưu; cơ chế lưu và bảo đảm giao dịch phải được hiểu theo module thực thi**. Phân biệt được ba tầng này giúp dùng hợp đồng CRUD của Commons chính xác và mở rộng sang những store khác mà không mang theo các giả định ngầm của một triển khai duy nhất.
