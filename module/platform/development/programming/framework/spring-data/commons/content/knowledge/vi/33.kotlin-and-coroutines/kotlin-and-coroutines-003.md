# Data class, constructor mặc định và giá trị tham số thiếu

## 1. Một giá trị mặc định có thể thuộc nhiều lớp khác nhau

Trong chương **Kotlin và coroutine** của module **SPRING_DATA_COMMONS**, Kotlin data class giúp mô tả entity và dữ liệu truy vấn bằng một primary constructor ngắn gọn. Tuy nhiên, cần xác định rõ ai tạo object và giá trị nào thực sự được truyền vào constructor.

Ví dụ:

~~~kotlin
data class Customer(
    val id: String,
    val displayName: String = "Chưa đặt tên"
)
~~~

Giá trị `"Chưa đặt tên"` là default argument của Kotlin. Nó không tự là:

- Một default constraint trong database.
- Một thao tác cập nhật các bản ghi cũ.
- Một quy tắc thay mọi chuỗi rỗng bằng tên mặc định.
- Một cách sửa mọi lỗi chuyển đổi dữ liệu.
- Một lời bảo đảm rằng mọi persistence provider đều gọi constructor giống nhau.

Khi đọc dữ liệu bằng Spring Data, object mapping của module phải lựa chọn constructor hoặc creator, lấy giá trị từ nguồn dữ liệu rồi tạo instance. Sự kết hợp giữa metadata Kotlin và khả năng của mapper quyết định default argument có được áp dụng hay không.

## 2. Kotlin áp dụng default argument khi đối số được bỏ qua

Với class trên, các lời gọi thông thường có ý nghĩa:

~~~kotlin
val first = Customer(id = "c-1")
val second = Customer(id = "c-2", displayName = "An")
val third = Customer(id = "c-3", displayName = "")

check(first.displayName == "Chưa đặt tên")
check(second.displayName == "An")
check(third.displayName == "")
~~~

Trong lời gọi thứ nhất, `displayName` bị bỏ qua nên Kotlin dùng biểu thức mặc định. Lời gọi thứ hai và thứ ba truyền giá trị cụ thể, nên Kotlin giữ giá trị được truyền.

Chuỗi rỗng không phải một đối số bị thiếu. Nếu nghiệp vụ không cho phép tên rỗng, cần xác thực riêng.

### 2.1. Truyền null không giống bỏ đối số

Với kiểu không nullable:

~~~kotlin
data class Customer(
    val id: String,
    val displayName: String = "Chưa đặt tên"
)
~~~

Lời gọi Kotlin trực tiếp sau không hợp lệ về kiểu:

~~~kotlin
// Không biên dịch: displayName có kiểu String, không phải String?.
Customer(id = "c-1", displayName = null)
~~~

Nếu tham số nullable, null trở thành một giá trị hợp lệ nhưng vẫn không có nghĩa là bỏ tham số:

~~~kotlin
data class Message(
    val text: String? = "Nội dung mặc định"
)

val omitted = Message()
val explicitNull = Message(text = null)

check(omitted.text == "Nội dung mặc định")
check(explicitNull.text == null)
~~~

Đây là quy tắc của lời gọi Kotlin thông thường. Cách một mapper chuyển dữ liệu thiếu hoặc null thành lời gọi constructor cần được xem xét thêm; không nên đồng nhất hai lớp này.

### 2.2. Biểu thức default được đánh giá khi cần dùng

Một default như `Instant.now()` hoặc `UUID.randomUUID()` là biểu thức thực thi, không phải hằng số cố định được lưu trong schema.

Nếu một mapper phải dùng default đó khi đọc một field bị thiếu, mỗi lần materialize có thể nhận một giá trị mới. Vì vậy, default động cần được dùng đúng mục đích, đặc biệt với ID, thời gian tạo và dữ liệu lịch sử.

## 3. “Constructor mặc định” là một cách gọi dễ gây nhầm

Ba khái niệm nên được tách riêng:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Primary constructor có default argument | `data class Label(val text: String = "Mới")` | Một số tham số có thể được bỏ qua khi gọi theo cơ chế Kotlin |
| Constructor không đối số | `constructor()` | Một constructor có chữ ký không nhận tham số |
| Giá trị default tại database | `DEFAULT 'DRAFT'` | Quy tắc tại kho dữ liệu khi thao tác ghi đáp ứng điều kiện áp dụng default |

Một constructor có vài tham số default chưa chắc là constructor không đối số. Nếu còn một tham số bắt buộc, caller vẫn phải cung cấp tham số đó.

### 3.1. Data class không bắt buộc có constructor rỗng để được object mapping

Ví dụ:

~~~kotlin
data class Customer(
    val id: String,
    val displayName: String = "Chưa đặt tên"
)
~~~

Ở đây, `id` bắt buộc. Không thể gọi `Customer()` trong Kotlin mà không cung cấp ID.

Các mapper Spring Data hỗ trợ Kotlin có thể tạo object thông qua primary constructor với dữ liệu được cung cấp từ store. Không cần thêm một constructor rỗng chỉ để loại bỏ mọi tham số bắt buộc.

### 3.2. Khi mọi tham số đều có default

~~~kotlin
data class DraftLabel(
    val text: String = "Mới",
    val visible: Boolean = false
)

val label = DraftLabel()
~~~

Trên JVM, trường hợp primary constructor có default cho mọi tham số còn có thể cung cấp constructor không đối số theo cơ chế của Kotlin. Điều đó không có nghĩa mọi mapper sẽ ưu tiên constructor rỗng thay vì primary constructor.

Các cơ chế constructor tổng hợp của Kotlin, `@JvmOverloads` hoặc plugin tạo no-arg phục vụ những mục đích tương tác và khởi tạo cụ thể. Chúng không phải cách thay thế cho việc xác định đúng creator mà persistence stack sử dụng.

## 4. Spring Data lựa chọn creator rồi mới áp dụng tham số

Trong object mapping của Spring Data, việc tạo entity gồm các bước khái quát:

~~~mermaid
flowchart LR
    A["Document hoặc row"] --> B["Chuyển đổi giá trị nguồn"]
    B --> C["Creator được mapper lựa chọn"]
    C --> D["Binding tham số và metadata Kotlin"]
    D --> E["Instance"]
    E --> F["Population thuộc tính còn lại nếu có"]
~~~

Với data class đơn giản, primary constructor là điểm khởi tạo quan trọng trong cơ chế mapping hỗ trợ Kotlin của Spring Data. Với model có nhiều đường khởi tạo, cần hiểu quy tắc lựa chọn creator của mapper đang dùng.

Spring Data có annotation `@PersistenceCreator` để chỉ định creator phù hợp trong những trường hợp được hỗ trợ:

~~~kotlin
import org.springframework.data.annotation.PersistenceCreator

data class Customer @PersistenceCreator constructor(
    val id: String,
    val displayName: String = "Chưa đặt tên"
)
~~~

Annotation thường không cần thiết cho một data class đơn giản có primary constructor rõ ràng. Nó cũng không biến một creator không tương thích với dữ liệu thành creator hợp lệ.

Không thêm hàng loạt constructor phụ chỉ để che lỗi mapping. Constructor được chọn phải có tham số và quy tắc có ý nghĩa với dữ liệu được lưu.

### 4.1. Thông tin Kotlin là một phần của hợp đồng runtime

Mapper cần nhận diện được cấu trúc constructor, tên tham số, tính nullable và default argument theo khả năng của stack đang dùng.

Một model biên dịch được không tự chứng minh mọi metadata và thành phần hỗ trợ Kotlin đã sẵn sàng khi chạy. Khi cấu hình module hoặc đóng gói ứng dụng thay đổi, cần kiểm chứng đường materialize thực tế thay vì chỉ kiểm tra lời gọi constructor trong unit test.

### 4.2. Không tự tạo hoặc gọi constructor tổng hợp

Compiler Kotlin có cơ chế tổng hợp để biểu diễn các default argument trên JVM. Ứng dụng không nên tự phụ thuộc vào mask tham số hoặc constructor tổng hợp như một API persistence.

Hãy khai báo model rõ ràng và dùng cơ chế mapping công khai của module. Chi tiết compiler không phải hợp đồng dữ liệu của ứng dụng.

## 5. Giá trị thiếu và null trong object mapping hỗ trợ Kotlin

Một điểm quan trọng của Spring Data là mapper có hỗ trợ Kotlin có thể nhận diện tham số có default. Khi nguồn dữ liệu không cung cấp giá trị hoặc trả null, cơ chế binding có thể bỏ tham số đó để Kotlin áp dụng default.

Vì vậy, đối với đường mapping này, dữ liệu nguồn null có thể dẫn tới default argument, dù lời gọi Kotlin trực tiếp với tham số nullable và giá trị null không làm như vậy.

Đây là hành vi của quá trình binding, không phải quy tắc “Kotlin luôn thay null bằng default”. Cần kiểm tra mapper, converter và module thực tế, đặc biệt nếu có custom conversion hoặc creator riêng.

### 5.1. Ma trận cần hiểu

| Khai báo tham số | Khi gọi Kotlin mà bỏ đối số | Khi mapper hỗ trợ Kotlin nhận giá trị thiếu/null |
| --- | --- | --- |
| `val name: String` | Không hợp lệ vì thiếu tham số bắt buộc | Không có default để dùng; không thể tạo một giá trị String hợp lệ từ null chỉ nhờ null-safety |
| `val name: String = "Mới"` | Dùng `"Mới"` | Có thể dùng default theo cơ chế binding tham số optional |
| `val note: String?` | Vẫn phải truyền đối số khi gọi trực tiếp | Có thể nhận null nếu đường mapping cung cấp null |
| `val note: String? = null` | Dùng null | Kết quả null không phân biệt được thiếu với null đã lưu |
| `val note: String? = "Mới"` | Dùng `"Mới"` | Không nên mặc định null nguồn được giữ nguyên; binding optional có thể chọn default |

Một tham số nullable không có default vẫn là tham số bắt buộc đối với cú pháp gọi Kotlin trực tiếp. Nullable nói về miền giá trị, còn default nói về khả năng bỏ đối số.

### 5.2. Các giá trị hợp lệ không phải là “thiếu”

Các giá trị sau cần được giữ theo dữ liệu nguồn nếu mapping hợp lệ:

- `0` cho một số nguyên.
- `false` cho một boolean.
- Chuỗi rỗng `""`.
- Một collection rỗng.

Không dùng kiểm tra truthy/falsy hoặc “giá trị có vẻ rỗng” để tự chuyển tất cả sang default. Đó là một quy tắc nghiệp vụ khác, cần được viết tường minh nếu thực sự mong muốn.

### 5.3. Default không xử lý mọi lỗi chuyển đổi

Nếu store chứa một chuỗi không chuyển đổi được vào một field số, có thể phát sinh lỗi ở bước conversion trước khi constructor được gọi.

Ví dụ, `sortOrder: Int = 0` không phải lời hứa rằng giá trị nguồn `"không-phải-số"` sẽ trở thành 0. Muốn có conversion đặc biệt phải thiết kế converter và quy tắc lỗi riêng.

## 6. Ví dụ document mapping với Kotlin data class

Ví dụ sau minh họa model cho Spring Data MongoDB. Các đoạn code cần một ứng dụng đã cấu hình mapping và repository phù hợp; chúng không phải cấu hình kết nối hoàn chỉnh.

~~~kotlin
import org.springframework.data.annotation.Id
import org.springframework.data.mongodb.core.mapping.Document

@Document("catalog_item")
data class CatalogItem(
    @field:Id val id: String? = null,
    val name: String,
    val displayLabel: String = "Chưa đặt nhãn",
    val sortOrder: Int = 0,
    val active: Boolean = false,
    val note: String? = null
)
~~~

`name` là tham số bắt buộc. Các field khác có default rõ ràng theo mục đích minh họa. Giá trị `id = null` cũng hỗ trợ biểu diễn một object mới chưa có ID; nó không phải lý do để bỏ qua kiểm tra ID ở mọi dữ liệu đã lưu.

### 6.1. Document cũ thiếu field mới

~~~json
{
  "_id": "item-1",
  "name": "Sổ tay"
}
~~~

Khi được materialize qua mapper hỗ trợ các default trên, object có thể nhận:

~~~text
id           = item-1
name         = Sổ tay
displayLabel = Chưa đặt nhãn
sortOrder    = 0
active       = false
note         = null
~~~

Default giúp model đọc được một số dữ liệu cũ trong quá trình tiến hóa schema. Tuy nhiên, nó chưa ghi bổ sung các field đó vào document gốc.

### 6.2. Document có null tường minh

~~~json
{
  "_id": "item-2",
  "name": "Bút chì",
  "displayLabel": null
}
~~~

Với cơ chế constructor defaulting được hỗ trợ, null của `displayLabel` có thể dẫn tới `"Chưa đặt nhãn"`. Nếu yêu cầu nghiệp vụ cần phân biệt “không có field” với “field đã bị xóa về null”, model này không giữ đủ sự phân biệt đó sau materialization.

### 6.3. Document có giá trị cụ thể

~~~json
{
  "_id": "item-3",
  "name": "Tập giấy",
  "displayLabel": "",
  "sortOrder": 0,
  "active": false
}
~~~

Chuỗi rỗng, số 0 và false là các giá trị được cung cấp, không phải trường hợp tự dùng default do thiếu tham số.

### 6.4. Document thiếu dữ liệu bắt buộc

~~~json
{
  "_id": "item-4"
}
~~~

`name` không nullable và không có default. Trong đường mapping thông thường, đây là một trường hợp không thể materialize model như đã khai báo; có thể xuất hiện lỗi khởi tạo được framework bọc lại.

Không nên giải quyết bằng cách đổi `name` thành nullable hoặc thêm một tên giả nếu tên thực sự là dữ liệu nghiệp vụ bắt buộc. Cần xác định dữ liệu cũ, schema và quy tắc chuyển đổi phù hợp.

## 7. Default khi đọc không phải migration hay default của database

Ba thao tác sau có tác dụng khác nhau:

| Cơ chế | Khi nào tác động? | Có sửa dữ liệu cũ chỉ nhờ đọc không? |
| --- | --- | --- |
| Default argument của constructor | Khi lời gọi creator bỏ tham số tương ứng | Không |
| Default tại database | Khi thao tác ghi thỏa điều kiện áp dụng của store | Không tự backfill mọi bản ghi cũ |
| Migration/backfill | Khi chạy thao tác chuyển đổi dữ liệu được thiết kế | Có thể, theo phạm vi thao tác |

Ví dụ, một SQL column có default không có nghĩa mọi lần insert một giá trị null đều được đổi thành default. Cần xét câu lệnh ghi, ràng buộc null và hành vi database cụ thể.

Tương tự, việc constructor dùng `"DRAFT"` không có nghĩa database đã có một default constraint tương ứng.

### 7.1. Query chạy trước object mapping

Nếu một document không lưu `displayLabel`, query tìm field có giá trị `"Chưa đặt nhãn"` không tự xét default Kotlin của model để quyết định document đó có khớp hay không.

Luồng xử lý thông thường là:

~~~text
Store áp dụng filter/sort/limit
    → trả dữ liệu nguồn
    → mapper tạo object Kotlin
~~~

Vì vậy, các document có cùng `displayLabel` sau khi đọc có thể không có cùng hình dạng dữ liệu được lưu.

Điều này ảnh hưởng derived query, Query by Example, count và projection. Không dùng giá trị nhìn thấy trên object làm bằng chứng rằng mọi bản ghi trong store đều chứa field đó.

### 7.2. Sort cũng dựa vào dữ liệu nguồn

Một mapper có thể biểu diễn `sortOrder` bị thiếu thành 0. Nhưng store đã sắp xếp dữ liệu trước khi mapper áp dụng default.

Nếu backend có quy tắc riêng cho field thiếu hoặc null, thứ tự đó không tự giống việc mọi dòng thực sự lưu số 0.

Nếu cần filter và sort có cùng ngữ nghĩa với model mới, có thể cần backfill, một query biểu diễn fallback rõ ràng hoặc một chiến lược chuyển đổi schema phù hợp.

## 8. Data class không đồng nghĩa bất biến hoàn toàn

Các `val` trong primary constructor thuận tiện cho constructor binding, nhưng `val` chỉ ngăn gán lại property qua API thông thường của Kotlin.

Một object được tham chiếu bởi property vẫn có thể mutable. Một `List` đọc qua interface Kotlin cũng không tự chứng minh không có ai thay đổi collection bên dưới.

Ví dụ:

~~~kotlin
data class Basket(
    val id: String,
    val tags: MutableList<String> = mutableListOf()
)

val first = Basket(id = "b-1")
val second = first.copy()

second.tags.add("gift")
check("gift" in first.tags)
~~~

`copy()` tạo bản sao nông: hai object trong ví dụ vẫn tham chiếu cùng collection. Đây là đặc tính model Kotlin, không phải một lỗi của repository.

Nếu cần bất biến theo nghiệp vụ, hãy kiểm soát cấu trúc dữ liệu và cách sao chép, không chỉ đổi `var` thành `val`.

### 8.1. Các property trong thân class là một nhóm khác

~~~kotlin
data class Label(
    val id: String,
    val text: String = "Mới"
) {
    var selected: Boolean = false
}
~~~

`selected` có initializer của property, không phải default argument của primary constructor. Nó cũng không được đưa vào các thành phần data class sinh tự động theo cùng cách với property trong primary constructor.

Mapper có thể còn population các property sau khi tạo instance tùy model và module. Không suy rằng mọi property có `= ...` đều đi qua cùng cơ chế constructor defaulting.

## 9. copy không áp dụng lại mọi default của constructor

Các tham số bị bỏ qua của `copy()` lấy giá trị từ instance nguồn. Chúng không tự quay về biểu thức default ban đầu của primary constructor.

~~~kotlin
data class Message(
    val text: String? = "Nội dung mặc định"
)

val original = Message(text = null)
val copied = original.copy()

check(copied.text == null)
~~~

Muốn thay một field, cần truyền giá trị mong muốn:

~~~kotlin
val changed = original.copy(text = "Nội dung mới")
~~~

Trong persistence model, `copy()` còn có thể giữ ID, version và các field khác của object cũ. Nó không tự tạo một entity mới theo nghĩa nghiệp vụ hay theo chiến lược nhận diện entity mới của module.

Nếu repository trả lại một instance sau khi lưu, ứng dụng cần hiểu và dùng kết quả đó theo hợp đồng của module, nhất là khi ID hoặc version được bổ sung. Không mặc định mọi lần lưu cập nhật chính instance bất biến đầu vào.

## 10. Projection thiếu field có thể bị default che đi

Giả sử query chỉ lấy ID và tên, nhưng ứng dụng lại map vào toàn bộ `CatalogItem`.

Nếu mapper cho phép và áp dụng default cho các field không có, object kết quả có thể trông như sau:

~~~text
active = false
sortOrder = 0
note = null
~~~

Những giá trị đó có thể là fallback do query không lấy field, không phải dữ liệu thực tế của bản ghi đầy đủ.

Nguy hiểm xuất hiện khi code coi object này là entity đầy đủ rồi dùng nó cho một thao tác ghi thay thế. Tùy store và API ghi, các field chưa đọc có thể bị ghi lại bằng fallback.

### 10.1. Dùng kiểu kết quả phù hợp với query

Một DTO rõ ràng hơn:

~~~kotlin
data class CatalogItemSummary(
    val id: String,
    val name: String
)
~~~

DTO này không tuyên bố biết active, note hoặc sortOrder. Nó giúp ranh giới dữ liệu đọc và dữ liệu đầy đủ trở nên dễ kiểm tra.

Projection không cần được thiết kế thành một entity có mọi default chỉ để query không lỗi. Hình dạng kết quả nên phản ánh những field query thực sự cung cấp.

### 10.2. Default ID không làm partial entity thành entity hợp lệ để ghi

Nếu query không lấy ID và model có `id: String? = null`, object có thể mất định danh cần thiết cho thao tác cập nhật.

Không nên tự tạo một ID ngẫu nhiên khi đọc để che trường hợp này. Cần chọn đúng projection, lấy đủ ID hoặc không đưa dữ liệu đọc thiếu vào đường ghi entity.

## 11. Default có thể làm mất ba trạng thái của cập nhật một phần

Một API patch thường cần phân biệt:

1. Client không gửi field: giữ nguyên giá trị.
2. Client gửi null: xóa giá trị nếu được phép.
3. Client gửi giá trị cụ thể: thay giá trị.

Nếu chỉ dùng `note: String? = null`, hai trường hợp đầu có thể cùng trở thành null sau binding. Nếu dùng một default khác, vẫn có thể làm mất thông tin nguồn theo một cách khác.

Có thể mô tả thay đổi bằng một model tường minh:

~~~kotlin
sealed interface NoteChange {
    object Keep : NoteChange
    data class Set(val value: String?) : NoteChange
}

data class UpdateNote(
    val note: NoteChange = NoteChange.Keep
)

fun applyNote(
    current: CatalogItem,
    command: UpdateNote
): CatalogItem = when (val change = command.note) {
    NoteChange.Keep -> current
    is NoteChange.Set -> current.copy(note = change.value)
}
~~~

Ở đây:

- `Keep` có nghĩa không đổi.
- `Set(null)` có nghĩa đặt về null.
- `Set("Ghi chú")` có nghĩa đặt nội dung mới.

Lớp tiếp nhận request phải chuyển dữ liệu nguồn thành model này đúng cách. Đoạn code không tự cấu hình JSON deserialization và không có nghĩa một mapper persistence bất kỳ sẽ tự tạo ba trạng thái giúp ứng dụng.

Model command của API và model entity có thể có các nhu cầu khác nhau. Không nên dùng cùng một data class chỉ vì các field có tên giống nhau.

## 12. Default động cần được giới hạn ở đúng thời điểm tạo mới

Xét model:

~~~kotlin
data class Entry(
    val id: String,
    val createdAt: Instant = Instant.now()
)
~~~

`Instant` trong ví dụ thuộc `java.time`. Nếu một đường đọc áp dụng default khi `createdAt` không có, kết quả là thời gian materialize, không phải bằng chứng về thời gian bản ghi được tạo.

Hai lần đọc cùng dữ liệu thiếu có thể cho hai giá trị khác nhau. Điều này làm sai cách diễn giải auditing và có thể che dữ liệu lịch sử chưa hoàn chỉnh.

Các lựa chọn cần được cân nhắc theo nghiệp vụ:

- Tạo timestamp tường minh trong luồng tạo mới, bằng một nguồn thời gian kiểm soát được.
- Dùng auditing đúng khả năng của module nếu đó là metadata do ứng dụng quản lý.
- Biểu diễn dữ liệu lịch sử chưa biết bằng kiểu/hợp đồng phù hợp.
- Backfill theo một quy tắc có căn cứ nếu cần chuẩn hóa dữ liệu cũ.

Không tự bịa thời điểm lịch sử chỉ để thỏa một kiểu không nullable.

Tương tự, một default cấp quyền cao, số dư giả hoặc trạng thái nghiệp vụ hoàn tất có thể làm dữ liệu thiếu trở nên trông hợp lệ. Default phải có ý nghĩa khi áp dụng cho dữ liệu nguồn, không chỉ giúp constructor chạy được.

## 13. Null-safety của Kotlin không thay thế kiểm tra dữ liệu

`String` và `String?` mô tả miền giá trị trong Kotlin. Chúng không tự tạo:

- Ràng buộc `NOT NULL` ở mọi database.
- Kiểm tra chuỗi không rỗng.
- Kiểm tra độ dài hoặc định dạng.
- Foreign key hay kiểm tra giá trị nghiệp vụ.

Ví dụ, `name: String` vẫn cho phép `""` hoặc chuỗi chỉ có khoảng trắng nếu không có validation riêng.

Một model có thể đặt điều kiện trong `init`:

~~~kotlin
data class ValidatedName(
    val value: String
) {
    init {
        require(value.isNotBlank()) {
            "Name must not be blank"
        }
    }
}
~~~

Nếu persistence creator đi qua điều kiện đó, dữ liệu cũ không hợp lệ cũng có thể làm materialization thất bại. Đây có thể là điều mong muốn, nhưng phải được đánh giá khi thay đổi schema hoặc quy tắc model.

Không nên đưa fallback ở mọi nơi để che dữ liệu hỏng. Hãy phân biệt một field mới có default hợp lệ với một invariant đang bị vi phạm.

## 14. Coroutine thay đổi cách chờ, không thay quy tắc constructor

Một repository coroutine có thể trả data class như sau trong module hỗ trợ:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CatalogItemRepository :
    CoroutineCrudRepository<CatalogItem, String> {

    fun findByActiveTrue(): Flow<CatalogItem>
}
~~~

Ví dụ này cần module và hạ tầng repository coroutine phù hợp; chỉ khai báo interface không tự làm mọi store hỗ trợ coroutine.

Khi tìm một item:

~~~kotlin
suspend fun requireItem(
    repository: CatalogItemRepository,
    id: String
): CatalogItem = repository.findById(id)
    ?: throw NoSuchElementException("Catalog item not found")
~~~

Cần phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| Repository trả null cho kết quả đơn phù hợp | Không tìm thấy bản ghi theo hợp đồng query |
| Tìm thấy dữ liệu nhưng creator không nhận được `name` hợp lệ | Lỗi materialize, không phải “không tìm thấy” |
| Một field optional được dùng default | Instance được tạo theo quy tắc binding của mapper |
| Coroutine bị hủy hoặc I/O lỗi | Một tín hiệu điều khiển/lỗi khác, không phải một field bị thiếu |

Không dùng một catch quá rộng rồi đổi mọi lỗi thành null. Cách đó có thể biến dữ liệu không hợp lệ, lỗi kết nối hoặc cancellation thành một thông báo “không có bản ghi” sai.

Với `Flow`, lỗi materialize có thể xuất hiện khi collect, không phải khi mới nhận đối tượng Flow. `suspend` và `Flow` không sửa được dữ liệu thiếu hay thêm default ngoài các quy tắc mapper đã có.

## 15. Đối chiếu khả năng của từng persistence stack

| Stack hoặc module | Điểm cần xác định |
| --- | --- |
| Object mapping của Spring Data có hỗ trợ Kotlin | Creator được chọn, binding optional, nullability và conversion |
| Spring Data MongoDB | Document thiếu field, field null, projection và converter ảnh hưởng thế nào tới constructor |
| Spring Data JDBC/R2DBC | Row/column thực sự được query trả về, mapping của module và sự khác biệt giữa query đầy đủ với projection |
| Spring Data JPA | Entity do JPA provider materialize; không mặc định áp dụng cùng đường constructor mapping của Commons |
| Module khác hoặc custom converter | Có đi qua cơ chế Kotlin defaulting đang xét hay đã thay thế đường khởi tạo |

Với JPA, yêu cầu constructor, proxy và cách provider điền state là một chủ đề riêng. Các plugin Kotlin dành cho JPA có thể hỗ trợ những yêu cầu đó, nhưng không phải lời hứa rằng một column null sẽ tự được thay bằng default argument trong primary constructor.

Với row mapping, một column không được chọn cũng chưa chắc đi tới creator giống hệt một column được chọn và có SQL NULL. Module hoặc custom mapper có thể xử lý hoặc báo lỗi trước đó. Không khái quát hành vi của document mapping thành quy tắc cho mọi driver.

## 16. Tiến hóa schema bằng default cần một kế hoạch rõ ràng

Giả sử thêm `displayLabel` vào model đang có dữ liệu cũ. Một cách triển khai có thể gồm:

1. Xác định default có đúng với dữ liệu cũ hay chỉ đúng khi tạo mới.
2. Cho phép đọc dữ liệu cũ theo hợp đồng đã chọn.
3. Cập nhật luồng ghi để lưu field mới khi cần.
4. Quyết định có backfill hay không, nhất là khi query/sort phụ thuộc field đó.
5. Sau khi dữ liệu đã chuẩn hóa, đánh giá lại fallback và các invariant.

Default constructor có thể là một phần của quá trình tương thích, nhưng không thay toàn bộ kế hoạch.

Đặc biệt, nếu fallback che cả một projection thiếu field, cần kiểm soát để code không tưởng rằng quá trình backfill đã hoàn thành chỉ vì mọi object trong ứng dụng đều có một giá trị.

## 17. Các tình huống cần kiểm chứng

Các tình huống dưới đây là tiêu chí thiết kế kiểm thử, không phải báo cáo đã chạy code hoặc xác nhận cấu hình module cụ thể:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Gọi constructor Kotlin bỏ optional argument | Default được dùng theo quy tắc ngôn ngữ |
| Gọi constructor với nullable argument bằng null | Null được giữ trong lời gọi trực tiếp |
| Nguồn thiếu field optional | Hành vi defaulting của mapper/module thực tế |
| Nguồn chứa null cho field có default | Xác nhận null được chuyển thành default hay được xử lý theo đường riêng |
| Nguồn thiếu field bắt buộc không có default | Không che lỗi bằng dữ liệu giả |
| Nguồn chứa 0, false hoặc chuỗi rỗng | Không tự coi là tham số thiếu |
| Nguồn sai kiểu | Conversion lỗi hoặc chạy đúng converter đã thiết kế |
| Query projection bỏ một số field | DTO và đường ghi không hiểu nhầm fallback là state đầy đủ |
| Lưu rồi đọc lại entity bất biến | ID, version và các giá trị được store bổ sung được sử dụng đúng |
| Field có default thời gian hoặc ID động | Không phát sinh lịch sử/định danh giả khi đọc |
| Dùng Flow hoặc suspend repository | Lỗi mapping được phân biệt với không tìm thấy và cancellation |
| Đổi từ mapper Commons sang JPA provider | Kiểm chứng lại constructor và null/default semantics |

Unit test chỉ gọi `CatalogItem(name = "Sổ tay")` chứng minh default argument của Kotlin, chưa chứng minh mapper xử lý document hoặc row thiếu field đúng như mong muốn.

Muốn kiểm chứng persistence, cần dữ liệu nguồn và module thực tế hoặc một phép materialize tương ứng. Khi đánh giá null và missing, phải tạo hai trường hợp riêng nếu store có khả năng phân biệt chúng.

## 18. Tự kiểm tra kiến thức

1. Vì sao `String?` không đồng nghĩa “có thể bỏ tham số” trong mọi lời gọi Kotlin?
2. Với `text: String? = "Mới"`, lời gọi trực tiếp truyền null khác việc mapper chọn bỏ tham số như thế nào?
3. Vì sao data class có một tham số bắt buộc vẫn có thể được Spring Data tạo qua primary constructor?
4. Một field mặc định là 0 trên object có chứng minh database đang lưu số 0 không?
5. Vì sao query và sort có thể không phản ánh fallback vừa được mapper áp dụng?
6. Tại sao `copy()` không phải cách tự khôi phục các default ban đầu hoặc tạo một entity mới hoàn chỉnh?
7. Khi nào một default động như `Instant.now()` làm sai cách diễn giải dữ liệu lịch sử?
8. Vì sao lỗi constructor trong coroutine không nên bị đổi thành kết quả “không tìm thấy”?

Điểm cần giữ khi dùng data class cho Spring Data là mô tả đúng miền giá trị và đường khởi tạo: default argument thuộc constructor, dữ liệu thiếu/null được giải thích bởi mapper, còn ràng buộc và default tại store thuộc một lớp khác. Khả năng đọc dữ liệu cũ chỉ có ý nghĩa khi các lớp đó thống nhất với hợp đồng nghiệp vụ và query của ứng dụng.
