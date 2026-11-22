# Điều kiện tiếp tục phân cấp đối với interface con trong Java 17

Trong Java 17, `sealed interface` cho phép thiết kế một hệ phân cấp kiểu có kiểm soát: interface cha xác định **những lớp và interface nào được phép kế thừa hoặc triển khai trực tiếp**. Khi một **interface con trực tiếp `extends` một `sealed interface`**, interface con phải công bố rõ cách phân cấp tiếp theo: **tiếp tục giới hạn bằng `sealed`** hoặc **mở rộng tự do bằng `non-sealed`**.

Quy tắc này quan trọng vì chỉ cần một nhánh được mở bằng `non-sealed`, các kiểu ở sâu hơn trong nhánh đó có thể tiếp tục mở rộng mà không cần tên của chúng xuất hiện trong `permits` của interface gốc.

> **Phạm vi:** Bài học sử dụng cú pháp **chính thức của Java 17**. Sealed classes và sealed interfaces đã được chuẩn hóa ở Java 17 (JEP 409), không cần bật `--enable-preview`. Nội dung tập trung vào **interface con**, đồng thời phân biệt với lớp triển khai khi cần.

## 1. Hai khái niệm cần xác định trước

Giả sử có hệ phân cấp:

```java
sealed interface Message permits TextMessage, BinaryMessage {}

sealed interface TextMessage extends Message permits PlainText {}
non-sealed interface BinaryMessage extends Message {}

record PlainText(String value) implements TextMessage {}
```

Ở đây:

- `Message` là **sealed interface cha**.
- `TextMessage` và `BinaryMessage` là **direct subinterfaces** của `Message` vì mỗi interface khai báo trực tiếp `extends Message`.
- `PlainText` là lớp record **trực tiếp triển khai** `TextMessage`, đồng thời là kiểu triển khai **gián tiếp** của `Message`.
- `permits TextMessage, BinaryMessage` của `Message` điều khiển **tầng con trực tiếp**, không tự động liệt kê mọi kiểu ở các tầng sâu hơn.

Sơ đồ quan hệ:

```text
Message                           (sealed)
├── TextMessage                   (sealed: tiếp tục giới hạn)
│   └── PlainText                 (record: không thể kế thừa thêm)
└── BinaryMessage                 (non-sealed: mở nhánh)
    └── Các interface/lớp mới    (theo quy tắc Java thông thường)
```

**Từ khóa “trực tiếp” quyết định quy tắc.** Một interface gián tiếp thuộc hệ phân cấp `Message` nhưng chỉ trực tiếp kế thừa `BinaryMessage` không bị yêu cầu dùng `sealed` hoặc `non-sealed` chỉ vì tổ tiên xa là `Message`.

## 2. Quy tắc bắt buộc với interface con trực tiếp của sealed interface

Theo **Java Language Specification (JLS) 17, §9.1.1.4**, nếu interface `Child` có một **direct superinterface** được khai báo `sealed`, thì `Child`:

1. Phải được phép kế thừa trực tiếp bởi interface cha, thông qua danh sách `permits` hoặc quy tắc suy ra danh sách `permits`.
2. Phải khai báo **một trong hai** modifier: `sealed` hoặc `non-sealed`.
3. Không được khai báo đồng thời `sealed` và `non-sealed`.
4. Không thể chọn `final`, vì **interface không được khai báo `final`**.

Ví dụ tối thiểu hợp lệ:

```java
sealed interface Parent permits RestrictedChild, OpenChild {}

sealed interface RestrictedChild extends Parent
        permits RestrictedImplementation {}

non-sealed interface OpenChild extends Parent {}

final class RestrictedImplementation implements RestrictedChild {}
```

Ví dụ **không hợp lệ**:

```java
sealed interface Parent permits Child {}

interface Child extends Parent {} // LỖI: thiếu sealed hoặc non-sealed
```

Việc tên `Child` đã xuất hiện trong `permits` **chưa đủ**: `Child` vẫn phải công bố chính sách mở rộng ở tầng tiếp theo. Từ khóa `abstract` cũng không thể thay thế `sealed` hoặc `non-sealed`, vì mọi interface vốn đã ngầm định là abstract.

| Interface con trực tiếp `extends` một sealed interface | Được phép trong Java 17? | Ý nghĩa |
| --- | --- | --- |
| `sealed interface Child extends Parent ...` | Có, nếu `Parent` cho phép `Child` và `Child` có các con trực tiếp hợp lệ | Tiếp tục kiểm soát các kiểu con trực tiếp của `Child`. |
| `non-sealed interface Child extends Parent {}` | Có, nếu `Parent` cho phép `Child` | Cho phép mở rộng nhánh `Child` theo các quy tắc kế thừa thông thường. |
| `interface Child extends Parent {}` | Không | Thiếu chính sách phân cấp bắt buộc. |
| `final interface Child extends Parent {}` | Không | `final` không phải modifier hợp lệ cho interface. |
| `sealed non-sealed interface Child extends Parent ...` | Không | Hai modifier xung đột. |

## 3. Chọn `sealed`: giới hạn tiếp ở tầng interface con

Khi khai báo `sealed interface Child extends Parent`, bản thân `Child` trở thành một ranh giới phân cấp mới. Nó phải xác định các lớp hoặc interface **được phép trực tiếp `implements`/`extends Child`**.

```java
sealed interface Document permits EditableDocument {}

sealed interface EditableDocument extends Document
        permits TextDocument, SpreadsheetDocument {}

final class TextDocument implements EditableDocument {}
record SpreadsheetDocument(int rows) implements EditableDocument {}
```

Có hai danh sách độc lập:

- `Document permits EditableDocument`: chỉ `EditableDocument` được trực tiếp kế thừa `Document`.
- `EditableDocument permits TextDocument, SpreadsheetDocument`: chỉ hai kiểu được nêu được trực tiếp triển khai `EditableDocument`.

`TextDocument` và `SpreadsheetDocument` không cần có mặt trong `Document.permits`, vì chúng **không trực tiếp** khai báo `implements Document`.

### 3.1. Kiểu con trực tiếp của `sealed interface` ở tầng tiếp theo phải làm gì?

| Kiểu con trực tiếp của `EditableDocument` | Hướng phân cấp hợp lệ |
| --- | --- |
| Interface con | Khai báo `sealed` hoặc `non-sealed`. |
| Class thông thường | Khai báo `final`, `sealed` hoặc `non-sealed`. |
| `record` | Được phép nếu được `permits`; record ngầm định là `final`. |
| `enum` | Có quy tắc ngầm định `final` hoặc `sealed` theo cấu trúc enum; vẫn phải là kiểu được phép. |

Như vậy, **interface con không có lựa chọn `final`**, nhưng class trực tiếp triển khai một sealed interface có lựa chọn đó. Không nên áp dụng máy móc ba modifier dành cho class sang interface.

### 3.2. Mỗi tầng `sealed` có danh sách `permits` riêng

Ví dụ phân cấp ba tầng:

```java
sealed interface Node permits CompositeNode {}

sealed interface CompositeNode extends Node permits BranchNode {}

sealed interface BranchNode extends CompositeNode permits LeafNode {}

record LeafNode(String value) implements BranchNode {}
```

`Node` cho phép `CompositeNode`; `CompositeNode` cho phép `BranchNode`; `BranchNode` cho phép `LeafNode`. Mỗi ranh giới chỉ kiểm soát **con trực tiếp** của nó, nên có thể mở rộng thành nhiều tầng mà vẫn biết rõ nhánh nào được cho phép.

**Lưu ý:** Một `sealed interface` phải có ít nhất một kiểu con trực tiếp được phép. Nếu không ghi `permits`, Java chỉ có thể suy ra từ những kiểu đủ điều kiện được khai báo **trong cùng compilation unit** (thường là cùng file `.java`); xem mục 6.

## 4. Chọn `non-sealed`: mở nhánh phân cấp từ interface con

`non-sealed interface Child extends Parent` thông báo rằng `Child` **không tiếp tục áp đặt giới hạn `permits` cho các kiểu con của nó**. Các interface và lớp khác có thể mở rộng hoặc triển khai `Child` theo các quy tắc truy cập, module và kế thừa thông thường.

```java
sealed interface Operation permits ReadOperation, WriteOperation {}

sealed interface ReadOperation extends Operation permits ReadById {}
non-sealed interface WriteOperation extends Operation {}

record ReadById(long id) implements ReadOperation {}

// Hợp lệ: mở rộng nhánh non-sealed bằng interface thường.
interface BatchWrite extends WriteOperation {}

// Hợp lệ: lớp triển khai interface thường này.
class InsertMany implements BatchWrite {}

// Hợp lệ: lớp triển khai trực tiếp WriteOperation.
class UpdateOne implements WriteOperation {}
```

`Operation` vẫn là `sealed`: không phải mọi kiểu mới đều được trực tiếp `implements Operation`. Tuy nhiên, `InsertMany` và `UpdateOne` được chấp nhận qua nhánh `WriteOperation` đã mở.

### 4.1. Interface cháu có bắt buộc dùng `non-sealed` không?

**Không.** Nếu direct superinterface của nó là `non-sealed`, interface cháu có thể được khai báo bình thường:

```java
sealed interface Root permits OpenBranch {}

non-sealed interface OpenBranch extends Root {}

interface Grandchild extends OpenBranch {} // Hợp lệ
class GrandchildImpl implements Grandchild {} // Hợp lệ
```

Ở đây, `Grandchild` **không trực tiếp `extends Root`**, nên không thuộc quy tắc bắt buộc `sealed`/`non-sealed` dành cho direct subinterface của sealed interface.

Ngược lại, đoạn sau không hợp lệ:

```java
sealed interface Root permits OpenBranch {}
non-sealed interface OpenBranch extends Root {}

non-sealed interface Grandchild extends OpenBranch {}
// LỖI: Grandchild không có direct superinterface nào là sealed.
```

`non-sealed` chỉ có thể được khai báo trên interface có **ít nhất một superinterface trực tiếp là `sealed`**. Đây là một modifier có ý nghĩa xác định điểm **mở lại** một nhánh đang bị khóa; không phải từ khóa dùng tùy ý ở mọi interface.

### 4.2. Đã mở một nhánh rồi có thể chủ động khóa lại không?

**Có.** Interface cháu có thể tự khai báo `sealed` để tạo một ranh giới mới, dù cha trực tiếp là `non-sealed`:

```java
sealed interface Event permits ExtensibleEvent {}
non-sealed interface ExtensibleEvent extends Event {}

// Tạo một nhánh sealed mới dưới interface đang mở.
sealed interface AuditEvent extends ExtensibleEvent permits AuditCreated {}
record AuditCreated(String actor) implements AuditEvent {}
```

Trong ví dụ này, `ExtensibleEvent` không chặn các kiểu mới, nhưng `AuditEvent` kiểm soát các kiểu trực tiếp triển khai `AuditEvent`. Một nhánh đã mở không khiến mọi hậu duệ buộc phải mở mãi mãi.

## 5. Ví dụ Java 17 hoàn chỉnh: vừa tiếp tục khóa, vừa mở một nhánh

Lưu toàn bộ ví dụ dưới đây vào file **`HierarchyDemo.java`**; mọi kiểu cùng compilation unit và không sử dụng preview.

```java
sealed interface Request permits Query, Command {
    String describe();
}

// Nhánh giới hạn: chỉ hai record bên dưới được triển khai Query.
sealed interface Query extends Request permits FindById, CountAll {}

// Nhánh mở: có thể thêm interface/lớp triển khai mới.
non-sealed interface Command extends Request {}

// Record là final ngầm định nên hợp lệ khi trực tiếp implements Query.
record FindById(long id) implements Query {
    @Override
    public String describe() {
        return "FindById: " + id;
    }
}

record CountAll() implements Query {
    @Override
    public String describe() {
        return "CountAll";
    }
}

// Không cần sealed/non-sealed: direct superinterface là Command (non-sealed).
interface BatchCommand extends Command {}

final class UpdateMany implements BatchCommand {
    @Override
    public String describe() {
        return "UpdateMany";
    }
}

public class HierarchyDemo {
    public static void main(String[] args) {
        Request[] requests = {
            new FindById(42),
            new CountAll(),
            new UpdateMany()
        };

        for (Request request : requests) {
            System.out.println(request.describe());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 HierarchyDemo.java
java HierarchyDemo
```

Kết quả:

```text
FindById: 42
CountAll
UpdateMany
```

Sơ đồ phân cấp:

```text
Request (sealed; permits Query, Command)
├── Query (sealed; permits FindById, CountAll)
│   ├── FindById (record, final ngầm định)
│   └── CountAll (record, final ngầm định)
└── Command (non-sealed)
    └── BatchCommand (interface thường)
        └── UpdateMany (final class)
```

Điểm then chốt là `UpdateMany` không nằm trong danh sách `Request.permits`, bởi nó không trực tiếp `implements Request`. Nó đi qua `BatchCommand` và `Command`. `Request` vẫn có thể được dùng làm kiểu chung cho cả ba đối tượng mà vẫn giới hạn được **những nhánh xuất phát trực tiếp từ gốc**.

## 6. Điều kiện của `permits` đối với interface con

Để một interface con trực tiếp `extends` sealed interface hợp lệ, cần đồng thời xét **quan hệ kế thừa, quyền được phép và vị trí khai báo**.

### 6.1. Danh sách `permits` phải khớp với quan hệ trực tiếp

```java
sealed interface Transport permits RoadTransport {}
non-sealed interface RoadTransport extends Transport {}
```

Ở đây `RoadTransport` xuất hiện trong `Transport.permits` **và** trực tiếp `extends Transport`, nên hợp lệ.

Hai lỗi thường gặp:

```java
// Ví dụ riêng, không ghép chung với mã hợp lệ ở trên.
sealed interface Parent permits Allowed {}

non-sealed interface Allowed extends Parent {}
non-sealed interface NotAllowed extends Parent {} // LỖI: chưa được Parent cho phép
```

```java
// Ví dụ riêng.
interface Other {}
sealed interface Parent permits NotItsChild {} // LỖI: NotItsChild không extends Parent
sealed interface NotItsChild extends Other permits Leaf {}
record Leaf() implements NotItsChild {}
```

Chỉ ghi tên trong `permits` không tự tạo quan hệ kế thừa; chính khai báo `extends` hoặc `implements` mới tạo quan hệ đó.

### 6.2. Có thể lược `permits` khi compiler suy ra được

Với các kiểu trực tiếp thuộc **cùng compilation unit**, Java 17 cho phép suy ra danh sách:

```java
sealed interface Notification {}

sealed interface SystemNotification extends Notification {}
non-sealed interface UserNotification extends Notification {}

record Shutdown() implements SystemNotification {}
```

Compiler suy ra `Notification` cho phép `SystemNotification` và `UserNotification`; đồng thời suy ra `SystemNotification` cho phép `Shutdown`. Những kiểu được suy ra phải có tên canonical và trực tiếp kế thừa/triển khai sealed interface tương ứng. Không được lược `permits` rồi để sealed interface không có kiểu con được phép.

Khi các kiểu con được đặt ở nhiều file riêng, viết `permits` tường minh giúp thể hiện rõ hợp đồng phân cấp và là cách phù hợp khi compiler không thể suy ra từ cùng compilation unit.

### 6.3. Các kiểu được phép phải cùng module hoặc cùng package tùy cấu trúc dự án

Theo JLS 17 §9.1.4:

| Môi trường khai báo sealed interface | Điều kiện vị trí cho các kiểu con trực tiếp được phép |
| --- | --- |
| **Named module** (có `module-info.java`) | Phải thuộc **cùng module** với sealed interface cha; có thể nằm ở package khác trong module nếu đáp ứng quy tắc truy cập. |
| **Unnamed module** (thường là ứng dụng không tổ chức bằng named module) | Phải thuộc **cùng package** với sealed interface cha. |

Ví dụ hai kiểu ở hai package khác nhau **trong cùng named module** có thể thuộc một phân cấp sealed hợp lệ, miễn là tên kiểu truy cập được và các khai báo `permits`/`extends` thống nhất. Trong ứng dụng dùng unnamed module, không thể mở rộng trực tiếp một sealed interface từ package khác bằng cách chỉ thêm tên vào `permits`.

Những quy tắc về package/module nêu trên áp dụng **cho quan hệ con trực tiếp của sealed interface**. Khi một nhánh đã chuyển thành `non-sealed`, các kiểu con của nhánh đó tuân theo quy tắc truy cập Java thông thường; không bị buộc cùng package/module **chỉ bởi tính sealed của tổ tiên gián tiếp**.

## 7. Trường hợp interface con có nhiều superinterface

Java cho phép một interface `extends` nhiều interface. Nếu **ít nhất một** direct superinterface là `sealed`, interface con vẫn phải khai báo `sealed` hoặc `non-sealed`, và phải được **tất cả sealed direct superinterface** của nó cho phép.

Ví dụ hợp lệ:

```java
sealed interface Printable permits PrintableAndExportable {}
sealed interface Exportable permits PrintableAndExportable {}

non-sealed interface PrintableAndExportable
        extends Printable, Exportable {}

class Report implements PrintableAndExportable {}
```

`PrintableAndExportable` phải có tên trong cả `Printable.permits` và `Exportable.permits`. Nếu bỏ khỏi một danh sách, quan hệ kế thừa tương ứng sẽ không hợp lệ dù interface con đã có `non-sealed`.

Nếu một interface con chỉ mở rộng những interface thông thường hoặc `non-sealed`, nó **không được khai báo `non-sealed`** vì không có sealed direct superinterface. Tuy nhiên, nó vẫn có thể tự chọn `sealed` để bắt đầu một giới hạn mới.

## 8. Lỗi biên dịch điển hình và cách sửa

### Lỗi A: Interface con không khai báo chính sách phân cấp

```java
sealed interface Device permits MobileDevice {}
interface MobileDevice extends Device {} // Sai
```

Cách sửa: khai báo `sealed` và liệt kê lớp/interface con trực tiếp, hoặc khai báo `non-sealed` nếu nhánh này được phép mở rộng:

```java
sealed interface Device permits MobileDevice {}
non-sealed interface MobileDevice extends Device {} // Đúng
```

### Lỗi B: Dùng `final` cho interface con

```java
sealed interface Service permits PaymentService {}
final interface PaymentService extends Service {} // Sai
```

`final` dùng để chặn **class** bị kế thừa. Với interface, nếu muốn đóng danh sách kiểu con trực tiếp thì dùng `sealed` cùng một hoặc nhiều kiểu con hợp lệ; không có `final interface`.

### Lỗi C: Khai báo `non-sealed` khi cha trực tiếp không sealed

```java
interface Base {}
non-sealed interface Child extends Base {} // Sai
```

Cách sửa là bỏ `non-sealed` nếu chỉ cần một interface thường:

```java
interface Base {}
interface Child extends Base {} // Đúng
```

### Lỗi D: Interface cha không cho phép interface con

```java
sealed interface AuthMethod permits PasswordAuth {}
non-sealed interface PasswordAuth extends AuthMethod {}
non-sealed interface TokenAuth extends AuthMethod {} // Sai
```

Cách sửa là đưa `TokenAuth` vào `AuthMethod.permits` nếu nó thực sự thuộc tập các nhánh trực tiếp mà thiết kế muốn hỗ trợ:

```java
sealed interface AuthMethod permits PasswordAuth, TokenAuth {}
non-sealed interface PasswordAuth extends AuthMethod {}
non-sealed interface TokenAuth extends AuthMethod {}
```

Đây là quyết định về thiết kế API, không chỉ là một thủ thuật để làm compiler hết báo lỗi. Mở rộng `permits` là mở rộng tập các trường hợp thuộc hợp đồng phân cấp của interface cha.

## 9. Khi nào chọn `sealed`, khi nào chọn `non-sealed` cho interface con?

| Bối cảnh | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Hệ thống có tập biến thể nghiệp vụ được quản lý chặt, chẳng hạn loại kết quả hoặc loại lệnh nội bộ | `sealed interface Child` | Tiếp tục duy trì danh sách biến thể trực tiếp rõ ràng. |
| Muốn khóa các nhánh gốc nhưng cho phép một nhóm tính năng tạo thêm kiểu riêng | `non-sealed interface Child` | Mở một điểm mở rộng có chủ đích mà vẫn giữ các nhánh trực tiếp của gốc được kiểm soát. |
| Xây dựng tầng con dưới một `non-sealed interface` và không muốn hạn chế thêm | `interface Grandchild` thông thường | Không có sealed direct superinterface nên không cần và không được thêm `non-sealed`. |
| Một phần của nhánh mở cần quay lại tập biến thể giới hạn | `sealed interface Grandchild` | Có thể chủ động tạo một ranh giới `permits` mới. |

Chọn `sealed` khi bạn **biết các kiểu con trực tiếp** và muốn quản lý việc thêm biến thể; chọn `non-sealed` khi chủ đích của API là cho phép các nhóm khác mở rộng nhánh đó. Dù lựa chọn nào, quyền truy cập của kiểu (`public`, package-private), phạm vi module và các ràng buộc API vẫn áp dụng.

## 10. Bài tập thực hành

**Bài 1 — Xác định tính hợp lệ**

Đoạn nào hợp lệ và vì sao?

```java
sealed interface Media permits Audio {}
sealed interface Audio extends Media permits Song {}
record Song(String title) implements Audio {}
```

```java
sealed interface Media permits Audio {}
interface Audio extends Media {}
```

```java
sealed interface Media permits Audio {}
non-sealed interface Audio extends Media {}
interface Podcast extends Audio {}
```

Gợi ý: kiểm tra lần lượt `permits`, quan hệ `extends`/`implements` trực tiếp, rồi modifier của interface con.

**Bài 2 — Mở một nhánh và khóa một nhánh**

Thiết kế `sealed interface Payment` với hai interface con:

- `CardPayment` chỉ cho phép các kiểu triển khai xác định trước.
- `CustomPayment` cho phép các nhóm khác tự tạo loại thanh toán.

Chọn modifier cho từng nhánh, viết `permits` phù hợp, rồi thêm một record cho `CardPayment` và một interface cháu thông thường dưới `CustomPayment`.

**Bài 3 — Kiểm tra phân cấp nhiều tầng**

Cho `Root (sealed) → Open (non-sealed) → Mid (interface thường) → Leaf (interface thường)`. Trả lời: `Leaf` có phải xuất hiện trong `Root.permits` không? `Mid` có cần `non-sealed` không? Nếu muốn kiểm soát tiếp con trực tiếp của `Mid`, sửa khai báo `Mid` như thế nào?

**Bài 4 — Nhiều interface cha**

Viết hai `sealed interface A` và `B`, cùng cho phép `non-sealed interface Both extends A, B`. Thử bỏ `Both` khỏi một trong hai danh sách `permits` và dự đoán lỗi dựa trên quy tắc JLS.

## 11. Tài liệu chính thức để tra cứu sâu hơn

- [JLS Java SE 17 §9.1.1.4 — `sealed` and `non-sealed` Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): yêu cầu modifier của interface có sealed direct superinterface.
- [JLS Java SE 17 §9.1.3 — Superinterfaces and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.3): cách xác định direct superinterface và quan hệ kế thừa.
- [JLS Java SE 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): danh sách `permits`, suy ra `permits` và giới hạn module/package.
- [JLS Java SE 17 §8.1.1.2 — `sealed`, `non-sealed`, and `final` Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): đối chiếu quy tắc dành cho class trực tiếp triển khai sealed interface.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): động cơ thiết kế và trạng thái chuẩn hóa ở JDK 17.

Khi đọc một hệ phân cấp sealed trong Java 17, hãy đi **từng cạnh kế thừa trực tiếp**: cha có cho phép con không, con khai báo `sealed` hay `non-sealed`, và nếu con tiếp tục `sealed` thì những kiểu nào được phép ở tầng kế tiếp. Làm như vậy sẽ xác định đúng điểm nào của hệ phân cấp đang bị giới hạn và điểm nào đã được mở rộng.
