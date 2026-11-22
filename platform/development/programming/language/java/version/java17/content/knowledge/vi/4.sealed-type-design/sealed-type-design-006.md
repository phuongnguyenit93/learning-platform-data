# Phép ép kiểu, các kiểu không thể giao nhau và kiểm tra của trình biên dịch trong Java 17

**Chủ đề:** Java 17  
**Chương:** Thiết kế với `sealed`  
**Bài học:** Phép ép kiểu, các kiểu không thể giao nhau và kiểm tra của trình biên dịch

Khi dùng kế thừa hoặc interface, lập trình viên thường ép một tham chiếu từ kiểu tổng quát sang một kiểu cụ thể hơn. Java kiểm tra phép ép kiểu trước khi chương trình chạy. Tuy nhiên, với phân cấp mở, trình biên dịch đôi khi không thể biết hết các lớp con có thể xuất hiện trong tương lai.

Từ Java 17, `sealed` class/interface là tính năng ngôn ngữ **ổn định**. Bằng cách khai báo chính xác các kiểu con trực tiếp được phép, `sealed` giúp trình biên dịch xác định nhiều trường hợp **hai kiểu không thể có cùng một đối tượng thực** (*disjoint types*). Nhờ đó, một số phép ép kiểu vô nghĩa bị chặn ngay lúc biên dịch thay vì chỉ thất bại khi chạy.

Bài học này tập trung vào ba câu hỏi:

1. Khi nào phép ép kiểu tham chiếu được chấp nhận ngay lúc biên dịch?
2. Java 17 xác định hai kiểu **không thể giao nhau** như thế nào, đặc biệt khi có `sealed`, `final` và `non-sealed`?
3. Sự khác nhau giữa **lỗi biên dịch**, **`ClassCastException` khi chạy** và **`instanceof` trả về `false`** là gì?

> **Phạm vi Java 17:** `sealed` đã được chuẩn hóa ở Java 17; pattern matching cho `instanceof` đã ổn định từ Java 16. Pattern matching cho `switch` vẫn là **preview** ở Java 17, vì vậy các ví dụ dưới đây dùng cú pháp Java 17 ổn định và không yêu cầu `--enable-preview`.

## 1. Phép ép kiểu tham chiếu là gì?

Trong Java, một biến tham chiếu có **kiểu tĩnh** được biết ở thời điểm biên dịch. Đối tượng mà biến tham chiếu trỏ tới có **kiểu thực tế** lúc chạy.

```java
interface Animal {}

final class Dog implements Animal {}

Animal animal = new Dog();   // Kiểu tĩnh: Animal; đối tượng thực tế: Dog
Dog dog = (Dog) animal;      // Ép kiểu từ Animal về Dog
```

Ở dòng ép kiểu:

- **Nguồn (source type, `S`):** `Animal` — kiểu tĩnh của biểu thức `animal`.
- **Đích (target type, `T`):** `Dog` — kiểu yêu cầu sau ép kiểu.
- **Kiểu thực tế tại runtime:** `Dog`, nên phép ép kiểu thành công.

Cú pháp ép kiểu không tạo đối tượng mới và không biến một đối tượng thành lớp khác. Nó yêu cầu hệ thống kiểu xem tham chiếu như kiểu đích, với kiểm tra lúc chạy khi cần.

### 1.1. Ba nhóm tình huống

**Chuyển lên kiểu cha (upcast, widening reference conversion):**

```java
Dog dog = new Dog();
Animal animal = dog;          // Không cần cast
Object value = (Object) dog;  // Cast tường minh nhưng không cần thiết
```

Vì mọi `Dog` đều là `Animal`, nên phép chuyển tương ứng luôn hợp lệ đối với tham chiếu không `null`. Trình biên dịch biết quan hệ này.

**Chuyển xuống kiểu con (downcast):**

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;      // Được biên dịch, thành công lúc chạy
```

Biến `Animal` *có thể* trỏ đến một `Dog`, nhưng không bắt buộc. Phép ép kiểu được chấp nhận tại thời điểm biên dịch; runtime phải kiểm tra đối tượng thật.

**Chuyển giữa hai interface hoặc từ class sang interface khác:**

```java
interface Auditable {}
interface Exportable {}

final class Report implements Auditable, Exportable {}

Auditable a = new Report();
Exportable e = (Exportable) a;  // Hợp lệ; đối tượng thật hỗ trợ cả hai
```

Hai interface có thể cùng được triển khai bởi một class. Việc chúng không có quan hệ `extends` trực tiếp không có nghĩa chúng luôn không thể giao nhau.

### 1.2. Phép ép kiểu có thể biên dịch nhưng vẫn thất bại khi chạy

```java
interface Animal {}

final class Dog implements Animal {}
final class Cat implements Animal {}

Animal animal = new Cat();

Dog dog = (Dog) animal;  // Biên dịch được; ném ClassCastException khi chạy
```

Tại thời điểm biên dịch, kiểu tĩnh là `Animal`, nên tham chiếu **có khả năng** chứa `Dog`. Trình biên dịch không kết luận chỉ từ kiểu tĩnh rằng phép cast nhất định sai. Tại runtime, đối tượng thật là `Cat`, không phải `Dog`, nên `ClassCastException` được ném ra.

Đây là ranh giới cơ bản: **“phép cast có thể thành công” khác với “phép cast chắc chắn thành công”.**

## 2. “Hai kiểu không thể giao nhau” nghĩa là gì?

Trong ngữ cảnh Java Language Specification (JLS), hai kiểu class/interface **disjoint** khi trình biên dịch có thể chứng minh rằng **không có đối tượng không phải `null` nào** đồng thời là instance của cả hai kiểu. Khi hai kiểu disjoint, nhiều phép ép kiểu giữa chúng bị loại ngay từ thời điểm biên dịch.

Có thể hiểu theo tập hợp:

```text
S: tập các đối tượng có thể là instance của S
T: tập các đối tượng có thể là instance của T

Có khả năng giao nhau: S ∩ T có thể chứa đối tượng
Không thể giao nhau: S ∩ T = ∅ (không tính null)
```

Ví dụ điển hình:

```java
final class Invoice {}
interface Printable {}

// KHÔNG HỢP LỆ:
static Printable convert(Invoice invoice) {
    return (Printable) invoice;
}
```

`Invoice` được khai báo `final` và không triển khai `Printable`. Không lớp nào có thể vừa là hậu duệ của `Invoice` vừa triển khai `Printable`, vì `Invoice` không thể có lớp con. Vậy hai kiểu này không thể giao nhau. Trình biên dịch từ chối phép cast.

Ngược lại:

```java
class DraftInvoice {}              // Không final
interface Printable {}

class PrintableDraft extends DraftInvoice implements Printable {}

static Printable convert(DraftInvoice invoice) {
    return (Printable) invoice;   // Có thể biên dịch
}
```

`DraftInvoice` hiện không trực tiếp triển khai `Printable`, nhưng một lớp con như `PrintableDraft` **có thể** làm cả hai. Vì thế, phép cast có cơ hội thành công và phải được kiểm tra trên đối tượng thực tế.

**Không thể giao nhau là kết luận về cấu trúc kiểu, không phải phỏng đoán từ dữ liệu cụ thể ở một lần chạy.**

## 3. Quy tắc cơ bản trước khi xét `sealed`

Java đã kiểm tra nhiều trường hợp phép cast bất khả thi trước Java 17. `sealed` mở rộng khả năng suy luận ấy bằng cách cung cấp thêm thông tin về các nhánh được phép.

| Cặp kiểu | Có thể giao nhau không? | Lý do |
|---|---|---|
| Lớp `Dog` và interface `Animal` mà `Dog implements Animal` | Có | Mọi `Dog` đều là `Animal` |
| Hai class thông thường hoàn toàn không có quan hệ thừa kế | Không | Một đối tượng không thể đồng thời kế thừa hai nhánh class độc lập |
| `final class Invoice` và interface `Printable` mà `Invoice` không implement | Không | `Invoice` không có lớp con để bổ sung interface |
| Lớp không `final` và interface chưa được lớp đó implement | Có thể | Một lớp con có thể triển khai interface |
| Hai interface mở, không có quan hệ `extends` | Có thể | Một class có thể triển khai cả hai |
| Interface `sealed` và interface khác | Phụ thuộc từng nhánh được phép | Nếu mọi nhánh đều không thể giao nhau, trình biên dịch có thể loại phép cast |

### 3.1. Hai class độc lập: không phải cứ “mở” là có thể giao nhau

```java
class Car {}
class House {}

static House asHouse(Car car) {
    return (House) car;  // LỖI BIÊN DỊCH
}
```

Cả `Car` và `House` đều không `final`, nhưng Java chỉ cho phép một class kế thừa trực tiếp từ một class cha. Không thể có lớp con nào đồng thời `extends Car` và `extends House`. Hai class độc lập này không thể giao nhau.

### 3.2. Hai interface mở: có thể có triển khai chung

```java
interface Searchable {}
interface Cacheable {}

final class SearchCache implements Searchable, Cacheable {}

static Cacheable asCacheable(Searchable value) {
    return (Cacheable) value;   // Có thể biên dịch
}
```

Vì có thể tồn tại class như `SearchCache`, trình biên dịch không loại phép cast. Nếu `value` thật sự tham chiếu đến một kiểu chỉ triển khai `Searchable`, runtime sẽ ném `ClassCastException`.

### 3.3. Lớp `final` và interface không được triển khai

```java
interface Trackable {}

final class ImmutablePoint {}

// KHÔNG HỢP LỆ:
static Trackable asTrackable(ImmutablePoint point) {
    return (Trackable) point;
}
```

Ở đây, `final` làm khả năng thêm interface qua lớp con biến mất. Điều này lý giải tại sao `final` có ý nghĩa lớn khi trình biên dịch đánh giá các kiểu disjoint.

## 4. `sealed` thay đổi cách trình biên dịch suy luận

Một interface `sealed` chỉ cho phép các kiểu con trực tiếp được liệt kê trong `permits`. Mỗi kiểu con trực tiếp phải tiếp tục được khai báo phù hợp là `final`, `sealed` hoặc `non-sealed`; record ngầm định `final`.

```java
sealed interface OperationResult permits Success, Failure {}

record Success(String message) implements OperationResult {}

record Failure(String reason) implements OperationResult {}
```

Nhờ mô hình này, trình biên dịch biết một đối tượng `OperationResult` phải thuộc một nhánh được phép. Vì cả hai record đều `final`, không thể xuất hiện một lớp con khác của các record để “lén” bổ sung interface ngoài mô hình.

### 4.1. Interface khác không giao với bất kỳ nhánh nào

```java
interface JsonWritable {}

sealed interface OperationResult permits Success, Failure {}

record Success(String message) implements OperationResult {}

record Failure(String reason) implements OperationResult {}

static JsonWritable asJson(OperationResult result) {
    return (JsonWritable) result;   // LỖI BIÊN DỊCH trên Java 17
}
```

Lập luận:

1. `OperationResult` chỉ cho phép `Success` và `Failure`.
2. `Success` và `Failure` đều là record, ngầm định `final`.
3. Không record nào triển khai `JsonWritable`.
4. Không có kiểu con khác của chúng để bổ sung `JsonWritable`.
5. Do đó, không có đối tượng không phải `null` nào vừa là `OperationResult` vừa là `JsonWritable`.

Ngay cả khi `JsonWritable` là interface mở, **phía `OperationResult` đã đóng hết các nhánh liên quan**, nên phép cast không còn cơ hội thành công.

### 4.2. Khi một nhánh có thể giao nhau, phép cast được phép

Sửa một nhánh để chính kiểu con triển khai `JsonWritable`:

```java
interface JsonWritable {
    String toJson();
}

sealed interface OperationResult permits Success, Failure {}

record Success(String message)
        implements OperationResult, JsonWritable {

    @Override
    public String toJson() {
        return "{\"message\":\"" + message() + "\"}";
    }
}

record Failure(String reason) implements OperationResult {}

static JsonWritable asJson(OperationResult result) {
    return (JsonWritable) result; // Có thể biên dịch
}
```

Phép cast **có thể** thành công nếu `result` chứa `Success`, nhưng sẽ thất bại tại runtime nếu nó chứa `Failure`.

Đoạn `toJson()` chỉ minh họa hợp đồng interface; trong ứng dụng thực tế, hãy dùng thư viện JSON phù hợp để escape dữ liệu chính xác.

### 4.3. Không phải hai interface khác nhau đều disjoint

Hai interface `sealed` có thể cùng cho phép một lớp triển khai:

```java
sealed interface Readable permits FileEntry {}

sealed interface Storable permits FileEntry {}

final class FileEntry implements Readable, Storable {}

static Storable asStorable(Readable readable) {
    return (Storable) readable;  // Hợp lệ
}
```

Mặc dù `Readable` và `Storable` không `extends` nhau, chúng có **`FileEntry` chung**. Vì vậy chúng không disjoint.

## 5. `non-sealed` mở lại khả năng tồn tại đối tượng chung

Giới hạn `permits` chỉ áp dụng cho **kiểu con trực tiếp**. Khi một nhánh được khai báo `non-sealed`, nhánh ấy mở trở lại theo quy tắc kế thừa thông thường. Trình biên dịch phải tính đến các lớp con có thể xuất hiện trong tương lai.

```java
sealed interface JobResult permits Done, ExtensionResult {}

record Done(String value) implements JobResult {}

non-sealed interface ExtensionResult extends JobResult {}

class FrameworkEvent {}

final class CustomResult extends FrameworkEvent
        implements ExtensionResult {}
```

Vì `CustomResult` vừa là `FrameworkEvent` vừa là `JobResult`, hai kiểu này **có thể giao nhau**. Xét phép cast:

```java
static FrameworkEvent convert(JobResult result) {
    return (FrameworkEvent) result;   // Có thể biên dịch
}
```

Nếu `result` là `CustomResult`, cast thành công. Nếu `result` là `Done`, cast thất bại lúc chạy. Việc `JobResult` là `sealed` không tự động chặn phép cast, vì một nhánh `non-sealed` đã cho phép giao nhau với `FrameworkEvent`.

### 5.1. Nhưng ép sang lớp `final` không liên quan vẫn bị từ chối

Thêm lớp:

```java
final class UnrelatedRecord {}
```

Lúc này:

```java
static UnrelatedRecord convert(JobResult result) {
    return (UnrelatedRecord) result;  // LỖI BIÊN DỊCH
}
```

`UnrelatedRecord` không triển khai `JobResult` hoặc `ExtensionResult`, và là lớp `final` nên không thể có lớp con bổ sung các interface ấy. Nhánh `non-sealed` cho phép một số kiểu giao nhau **không có nghĩa mọi kiểu đích đều có thể giao nhau**.

### 5.2. So sánh hai tình huống trong cùng cây

```text
JobResult (sealed)
├── Done (record, final)
└── ExtensionResult (non-sealed interface)
    └── CustomResult (extends FrameworkEvent)

FrameworkEvent (class mở)
└── CustomResult (implements ExtensionResult)

UnrelatedRecord (final class, không implements JobResult)
```

| Source | Target | Kết quả biên dịch | Vì sao |
|---|---|---|---|
| `JobResult` | `Done` | Cho phép | `Done` là nhánh được phép |
| `JobResult` | `FrameworkEvent` | Cho phép | Có thể có lớp vừa extends `FrameworkEvent` vừa implements `ExtensionResult` |
| `JobResult` | `UnrelatedRecord` | Từ chối | Lớp đích `final` và không tham gia nhánh nào |
| `FrameworkEvent` | `JobResult` | Cho phép trong mô hình này | `CustomResult` là hậu duệ chung |
| `Done` | `UnrelatedRecord` | Từ chối | Hai class độc lập, không thể có cùng instance |

## 6. Trình biên dịch xét “có thể” chứ không đoán giá trị runtime

Một nguyên tắc hữu ích là: **quy tắc cast nhìn vào kiểu tĩnh của biểu thức và cấu trúc phân cấp đã khai báo**, không chỉ nhìn vào đối tượng cụ thể mà người viết biết sẽ được tạo ở một dòng code.

Giả sử:

```java
JobResult result = new Done("OK");
FrameworkEvent event = (FrameworkEvent) result;
```

Phép cast trên vẫn có thể **qua bước kiểm tra kiểu lúc biên dịch** vì cây `JobResult` có nhánh `ExtensionResult` và loại `CustomResult` có thể nằm trong cả hai tập. Nhưng ở thời điểm chạy, đối tượng là `Done`, nên Java ném `ClassCastException`.

Nếu thay kiểu tĩnh bằng `Done`:

```java
Done result = new Done("OK");
FrameworkEvent event = (FrameworkEvent) result; // LỖI BIÊN DỊCH
```

`Done` là một record, tức class `final`, và không kế thừa `FrameworkEvent`. Trình biên dịch có đủ thông tin để loại phép cast.

Điều này tạo nên khác biệt quan trọng:

| Kiểu tĩnh của biểu thức | Dữ liệu runtime | Java có thể kết luận gì? |
|---|---|---|
| `JobResult` | `Done` | Chỉ biết `JobResult` có nhánh khác có thể giao với `FrameworkEvent`; cast được phép nhưng runtime thất bại |
| `JobResult` | `CustomResult` | Cast được phép; runtime thành công |
| `Done` | `Done` | `Done` và `FrameworkEvent` là hai class không thể giao nhau; bị chặn ngay lúc biên dịch |

Không nên kết luận một phép ép kiểu “an toàn” chỉ vì `javac` chấp nhận nó.

## 7. `instanceof` chịu kiểm tra tương thích kiểu tương tự

Với `instanceof`, Java kiểm tra điều kiện kiểu ở runtime rồi trả về `true` hoặc `false`. Nhưng **bản thân biểu thức `instanceof` phải hợp lệ lúc biên dịch**.

### 7.1. Phân biệt ép kiểu với kiểm tra kiểu

```java
static String describe(JobResult result) {
    if (result instanceof Done done) {
        return "Hoàn tất: " + done.value();
    }
    if (result instanceof FrameworkEvent) {
        return "Nhánh mở rộng";
    }
    return "Kết quả khác";
}
```

Ở đây:

- `result instanceof Done done` kiểm tra đối tượng và, nếu khớp, tạo biến mẫu `done` có kiểu `Done`. Pattern matching cho `instanceof` là tính năng ổn định từ Java 16.
- `result instanceof FrameworkEvent` có thể biên dịch vì `JobResult` có nhánh `non-sealed`; biểu thức nhận `true` hoặc `false` tùy đối tượng thật.
- Không có phép cast nào trong ví dụ ném `ClassCastException`; kiểm tra không khớp thì biểu thức `instanceof` trả về `false`.

### 7.2. Nếu hai kiểu disjoint, `instanceof` cũng bị từ chối

```java
static boolean wrong(JobResult result) {
    return result instanceof UnrelatedRecord;  // LỖI BIÊN DỊCH
}
```

Trình biên dịch không đợi runtime để trả `false` vì quy tắc kiểu đã chứng minh không có đối tượng chung. Đây là kiểm tra hợp lệ của **biểu thức**, không phải suy diễn một nhánh `if` luôn sai rồi bỏ qua nhánh đó.

### 7.3. Pattern matching cho `instanceof` có thêm quy tắc riêng

Java 17 có hai dạng thường gặp:

```java
if (result instanceof Done) {
    // Kiểm tra kiểu theo cách thông thường.
}

if (result instanceof Done done) {
    // Kiểm tra kiểu và tạo biến mẫu done.
}
```

Trong Java 17, dạng **type pattern** còn bị từ chối nếu kiểu tĩnh bên trái **đã là subtype** của kiểu pattern. Ví dụ:

```java
Done done = new Done("OK");

// KHÔNG HỢP LỆ: Done đã là subtype của JobResult.
if (done instanceof JobResult another) {
    System.out.println(another);
}
```

Dạng kiểm tra thông thường `done instanceof JobResult` có thể được dùng, nhưng thường dư thừa vì một `Done` không `null` luôn là `JobResult`. Quy tắc từ chối trường hợp “pattern hiển nhiên luôn khớp với kiểu đối tượng” là **quy tắc riêng của pattern matching**, không đồng nghĩa `Done` và `JobResult` disjoint.

### 7.4. Phạm vi biến mẫu

Biến `done` chỉ được sử dụng ở những vị trí mà Java chứng minh biểu thức pattern đã khớp:

```java
static String label(JobResult result) {
    if (result instanceof Done done) {
        return done.value();    // Hợp lệ trong nhánh true
    }
    return "Không phải Done";
}
```

Không thể mặc định biến `done` tồn tại ngoài phạm vi nơi điều kiện được xác nhận. Quy tắc phạm vi này giúp tránh truy cập giá trị chưa được xác lập.

## 8. Kiểm tra lúc biên dịch và lỗi lúc chạy

| Trường hợp | Lúc biên dịch | Lúc chạy |
|---|---|---|
| Cast từ kiểu con lên kiểu cha | Chấp nhận | Thành công; thường không cần kiểm tra thêm |
| Cast giữa hai kiểu có khả năng giao nhau | Chấp nhận | Có thể thành công hoặc ném `ClassCastException` |
| Cast giữa hai kiểu đã chứng minh disjoint | **Lỗi biên dịch** | Không thể chạy đoạn mã đó nếu giữ nguyên |
| `instanceof` giữa hai kiểu có khả năng giao nhau | Chấp nhận | Trả `true` hoặc `false` |
| `instanceof` giữa hai kiểu đã chứng minh disjoint | **Lỗi biên dịch** | Không chạy đoạn mã đó |
| `instanceof` với giá trị `null` và biểu thức hợp lệ | Chấp nhận | Trả `false` |
| Cast tham chiếu `null` qua một phép chuyển kiểu hợp lệ | Chấp nhận | Giá trị kết quả vẫn là `null` |

### 8.1. Vì sao `null` không làm quy tắc disjoint mất hiệu lực?

Mô tả chính xác của disjoint types loại trừ `null` vì `null` không phải instance của class/interface nào. Tuy vậy, quy tắc kiểm tra cast dựa vào **kiểu tĩnh**, nên một phép cast đã bị cấm không được hợp thức hóa chỉ vì biến hiện có giá trị `null`.

Ví dụ:

```java
final class Alpha {}
final class Beta {}

Alpha alpha = null;

// LỖI BIÊN DỊCH vì Alpha và Beta là hai class độc lập:
Beta beta = (Beta) alpha;
```

Ngược lại, ép từ biểu thức kiểu `Object` sang `Beta` là phép chuyển có thể hợp lệ:

```java
Object value = null;
Beta beta = (Beta) value;      // Hợp lệ; beta == null
boolean test = value instanceof Beta;  // Hợp lệ; kết quả false
```

Đừng dùng `null` để suy luận rằng compiler sẽ cho phép mọi phép cast giữa các kiểu bất kỳ.

### 8.2. Ép qua `Object` có thể che thông tin kiểu tĩnh

```java
JobResult result = new Done("OK");

Object broad = result;  // Mở rộng kiểu tĩnh sang Object

try {
    UnrelatedRecord record = (UnrelatedRecord) broad;
    System.out.println(record);
} catch (ClassCastException exception) {
    System.out.println("Đối tượng không phải UnrelatedRecord");
}
```

Bước cast từ `Object` sang `UnrelatedRecord` có thể biên dịch vì biến `Object` có thể trỏ tới một đối tượng `UnrelatedRecord`. Nhưng đối tượng thật vẫn là `Done`, nên runtime ném `ClassCastException`.

Việc đi vòng qua `Object`, raw type hoặc reflection **không thay đổi kiểu thật của đối tượng**. Nó chỉ làm trình biên dịch mất bớt thông tin kiểu ở một điểm kiểm tra; không phải cách giải quyết đúng khi hai kiểu vốn không tương thích.

## 9. Trình biên dịch suy luận dọc nhiều tầng `sealed`

Không chỉ xét mỗi `permits` ở gốc: trình biên dịch có thể tiếp tục đi xuống các nhánh `sealed` khác.

```java
interface Auditable {}

sealed interface Message permits UserMessage, SystemMessage {}

sealed interface UserMessage extends Message
        permits TextMessage, ImageMessage {}

record TextMessage(String text) implements UserMessage {}

record ImageMessage(byte[] bytes) implements UserMessage {}

record SystemMessage(String code) implements Message {}
```

Trong mô hình này:

```text
Message (sealed)
├── UserMessage (sealed)
│   ├── TextMessage (record/final)
│   └── ImageMessage (record/final)
└── SystemMessage (record/final)

Auditable (interface mở, không có kiểu nào ở trên triển khai)
```

Phép cast sau bị loại:

```java
static Auditable asAuditable(Message message) {
    return (Auditable) message;  // LỖI BIÊN DỊCH
}
```

Mặc dù `UserMessage` là một interface, nó cũng `sealed` và các nhánh `TextMessage`, `ImageMessage` đều đóng. Không nhánh nào có thể tạo đối tượng vừa là `Message` vừa là `Auditable`.

Nếu thay `UserMessage` bằng `non-sealed interface`, thì lớp mới có thể triển khai cả `UserMessage` và `Auditable`. Khi đó kết luận disjoint có thể không còn đúng, và compiler có thể chấp nhận phép cast.

**Tư duy cần nhớ:** Với phân cấp `sealed` nhiều tầng, hãy lần theo các nhánh cho đến khi gặp kiểu `final`, một nhánh `non-sealed` hoặc kiểu có thể tạo giao điểm với đích cần cast.

## 10. Ví dụ hoàn chỉnh chạy trên Java 17

Ví dụ này minh họa đồng thời:

- Kiểm tra kiểu bằng `instanceof` và pattern matching.
- Một phép cast **có thể thành công** nhờ nhánh `non-sealed`.
- Một phép cast **vẫn được biên dịch** nhưng thất bại lúc chạy và ném `ClassCastException`.

Lưu mã vào file **`SealedCastDemo.java`**:

```java
public class SealedCastDemo {

    sealed interface Response
            permits Accepted, Rejected, Extension {}

    record Accepted(String id) implements Response {}

    record Rejected(String reason) implements Response {}

    non-sealed interface Extension extends Response {}

    static class ExternalBase {
        String source() {
            return "external";
        }
    }

    static final class PartnerResponse extends ExternalBase
            implements Extension {}

    static final class Unrelated {}

    static String describe(Response response) {
        if (response instanceof Accepted accepted) {
            return "Accepted: " + accepted.id();
        }
        if (response instanceof Rejected rejected) {
            return "Rejected: " + rejected.reason();
        }
        if (response instanceof ExternalBase base) {
            return "Extension: " + base.source();
        }
        return "Other extension";
    }

    static ExternalBase asExternalBase(Response response) {
        // Hợp lệ vì có thể tồn tại Response cũng là ExternalBase.
        return (ExternalBase) response;
    }

    public static void main(String[] args) {
        Response fromPartner = new PartnerResponse();
        Response fromCore = new Accepted("R-17");

        System.out.println(describe(fromPartner));
        System.out.println(describe(fromCore));

        ExternalBase converted = asExternalBase(fromPartner);
        System.out.println(converted.source());

        try {
            // Được phép về kiểu tĩnh; thất bại với đối tượng Accepted.
            asExternalBase(fromCore);
        } catch (ClassCastException exception) {
            System.out.println("Cast thất bại tại runtime");
        }

        // Nếu bỏ comment, phép cast dưới đây lỗi ngay khi biên dịch:
        // Unrelated value = (Unrelated) fromCore;
    }
}
```

Dùng JDK 17:

```bash
javac --release 17 SealedCastDemo.java
java SealedCastDemo
```

Kết quả dự kiến:

```text
Extension: external
Accepted: R-17
external
Cast thất bại tại runtime
```

Điểm đáng chú ý: `asExternalBase` nhận kiểu tĩnh `Response`, trong khi `Response` có nhánh `Extension` mở. Vì vậy, compiler **không** thể bác bỏ việc nó nhận một `PartnerResponse`. Tính hợp lệ theo kiểu tĩnh không giúp dự đoán đối tượng thật là `Accepted` ở một lần gọi cụ thể.

## 11. Kiểm tra của trình biên dịch còn liên quan đến `permits` và tính hợp lệ của cây

Bên cạnh kiểm tra cast, `javac` còn xác thực **cấu trúc phân cấp `sealed`**:

### 11.1. Kiểu con trực tiếp phải được cho phép

```java
sealed interface AccessResult permits Allow {}

final class Allow implements AccessResult {}

// KHÔNG HỢP LỆ: Deny không có trong permits.
final class Deny implements AccessResult {}
```

Trình biên dịch ngăn kiểu triển khai trực tiếp ngoài danh sách đã khai báo. Đây là cơ sở để nó tin rằng phân cấp được kiểm soát.

### 11.2. Kiểu con phải quyết định cách tiếp tục phân cấp

```java
sealed class BaseResult permits ChildResult {}

// KHÔNG HỢP LỆ: ChildResult cần final, sealed hoặc non-sealed.
class ChildResult extends BaseResult {}
```

Sửa bằng một trong các lựa chọn phù hợp:

```java
sealed class BaseResult permits ChildResult {}

final class ChildResult extends BaseResult {}
```

Có thể dùng `sealed` cho nhánh nhiều tầng, hoặc `non-sealed` khi chủ ý cho phép mở rộng. Quyết định ở mỗi tầng ảnh hưởng trực tiếp tới kết luận “có thể giao nhau” khi cast.

### 11.3. Kiểu con phải trực tiếp kế thừa hoặc triển khai đúng cha

```java
sealed interface Task permits Parent, Grandchild {}

non-sealed interface Parent extends Task {}

// KHÔNG HỢP LỆ khi liệt kê Grandchild trong permits của Task:
// Grandchild chỉ extends Parent, không trực tiếp extends Task.
interface Grandchild extends Parent {}
```

Danh sách `permits` không phải danh sách mọi hậu duệ. Chỉ những kiểu con **trực tiếp** được liệt kê. Khi đã ở dưới một nhánh `non-sealed`, hậu duệ sâu hơn không cần đưa vào `permits` của gốc.

### 11.4. Các kiểu con phải thuộc module/package phù hợp

Trong **named module**, các kiểu con trực tiếp được phép phải ở cùng module với kiểu `sealed`. Trong **unnamed module**, chúng phải ở cùng package.

Nhờ các ràng buộc này, danh sách các nhánh trực tiếp không thể bị bổ sung tùy ý từ một module bên ngoài. Đối với extension point của plugin ngoài module, cần cân nhắc thiết kế một nhánh `non-sealed` phù hợp hoặc để interface mở.

## 12. Những điểm dễ nhầm lẫn

### 12.1. “Hai interface không liên quan thì luôn cast sai”

**Không đúng.** Hai interface mở có thể cùng được triển khai bởi một class. Thậm chí hai interface `sealed` vẫn có thể có kiểu con chung nếu cấu trúc `permits` cho phép.

### 12.2. “Nếu mã `instanceof` luôn trả `false` thì Java sẽ chấp nhận và tối ưu hóa”

**Không nhất thiết.** Khi hai kiểu đã được chứng minh không thể giao nhau, `instanceof` là biểu thức không hợp lệ về kiểu và có thể bị từ chối lúc biên dịch.

### 12.3. “Có `sealed` là compiler biết hết mọi kiểu đối tượng của phân cấp”

**Chưa chính xác.** Nó biết các nhánh trực tiếp được phép. Nếu một nhánh `non-sealed` xuất hiện, các kiểu con mới vẫn có thể được thêm vào nhánh đó.

### 12.4. “Ép kiểu biên dịch được nghĩa là an toàn”

**Không đúng.** Nó chỉ có nghĩa phép chuyển không bị chứng minh là bất khả thi theo các quy tắc tĩnh. Runtime vẫn có thể ném `ClassCastException`.

### 12.5. “`final` và `sealed` kiểm soát quyền truy cập bảo mật”

**Không đúng.** Chúng điều khiển khả năng kế thừa/triển khai tại mức ngôn ngữ và hỗ trợ kiểm tra kiểu; không thay thế xác thực, phân quyền hay validation.

### 12.6. “`instanceof` pattern matching và pattern matching for `switch` đều chuẩn ở Java 17”

**Không đúng.** Pattern matching cho `instanceof` chuẩn từ Java 16, còn pattern matching cho `switch` chỉ là *preview* ở Java 17. Để viết ví dụ chạy mặc định trên Java 17, ưu tiên `instanceof` và các cấu trúc đã ổn định.

### 12.7. “Mọi phép cast bị từ chối đều do `sealed`”

**Không đúng.** Những quy tắc như hai class độc lập không thể có đối tượng chung hoặc `final class` không triển khai một interface đã tồn tại từ trước. `sealed` mở rộng khả năng chứng minh disjoint khi biết các nhánh được phép.

## 13. Quy trình suy luận khi đọc một phép cast

Khi gặp `(Target) source` hoặc `source instanceof Target`, có thể phân tích theo thứ tự:

1. **Xác định kiểu tĩnh của `source`**, không đánh đồng với đối tượng được khởi tạo ở một dòng cụ thể.
2. **Xác định `Target`** và quan hệ cha–con trực tiếp, gián tiếp.
3. Nếu là hai class độc lập, kiểm tra khả năng giao nhau qua hệ phân cấp class (Java chỉ có đơn kế thừa class).
4. Nếu có class `final`, xem class đó có trực tiếp/gián tiếp triển khai interface cần đối chiếu hay không.
5. Nếu có class/interface `sealed`, theo các kiểu trong `permits` xuống các nhánh con.
6. Khi gặp `non-sealed` hoặc class có thể mở rộng, cân nhắc liệu một lớp con tương lai có thể đồng thời thỏa cả hai kiểu.
7. Nếu **chứng minh không có kiểu đối tượng chung**, phép cast/kiểm tra `instanceof` tương ứng bị từ chối lúc biên dịch.
8. Nếu **có khả năng giao nhau**, phép cast có thể biên dịch, nhưng phải xét runtime; dùng `instanceof` để kiểm tra khi cần và tránh cast mù.

**Lưu ý:** Đây là phương pháp suy luận cho các ví dụ class/interface phổ biến. Java Language Specification còn có các quy tắc riêng cho generics, mảng, intersection types và type variables. Khi gặp kiểu phức tạp, phải áp dụng quy tắc chính thức ở JLS `5.1.6 và `5.5` thay vì suy diễn đơn giản từ sơ đồ cây.

### Bảng quyết định nhanh

| Quan sát | Kết luận thực hành |
|---|---|
| `S` là subtype của `T` | Upcast hợp lệ, thường không cần ép kiểu |
| `T` là subtype của `S` | Có thể downcast, nhưng cần kiểm tra runtime |
| Hai class không thuộc cùng chuỗi kế thừa | Không thể cast trực tiếp giữa chúng |
| Class `final` không implement interface đích | Không thể cast trực tiếp giữa hai kiểu đó |
| `sealed` với mọi nhánh đóng, không nhánh nào giao với đích | Compiler có thể chứng minh disjoint và từ chối |
| `sealed` có nhánh `non-sealed` có thể giao với đích | Cast có thể được phép; kết quả phụ thuộc đối tượng |
| Cast từ `Object` về kiểu cụ thể | Có thể biên dịch; không bảo đảm đối tượng thực tế đúng kiểu |

## 14. Luyện tập suy luận

**Bài 1.** Đọc khai báo:

```java
sealed interface A permits A1, A2 {}

record A1() implements A {}
record A2() implements A {}

interface B {}
```

Phép cast `(B) someA`, trong đó `someA` có kiểu tĩnh `A`, có thể biên dịch trên Java 17 không?

**Đáp án:** Không. `A` chỉ có hai nhánh cuối `A1` và `A2`; không nhánh nào triển khai `B`. Hai interface `A` và `B` không có instance chung, nên disjoint.

**Bài 2.** Giữ `A` nhưng đổi một nhánh:

```java
sealed interface A permits A1, APlugin {}

record A1() implements A {}

non-sealed interface APlugin extends A {}

interface B {}
```

`(B) someA` còn chắc chắn bị từ chối không?

**Đáp án:** Không. Có thể xuất hiện class triển khai đồng thời `APlugin` và `B`. Vì vậy, với kiểu tĩnh `A`, cast sang `B` có thể được biên dịch, nhưng có thể thất bại ở runtime.

**Bài 3.** Hai interface `Left` và `Right` đều `sealed`, nhưng cùng cho phép `Both`, còn `Both` là class `final` implements cả hai. Chúng có disjoint không?

**Đáp án:** Không. `Both` là đối tượng chung hợp lệ.

**Bài 4.** Một biến có kiểu tĩnh `A` đang trỏ tới `A1`. Trong mô hình của Bài 2, vì sao `(B) someA` có thể qua kiểm tra biên dịch nhưng vẫn ném `ClassCastException`?

**Đáp án:** Kiểu tĩnh `A` có nhánh `APlugin` mở, nên tồn tại khả năng giao nhau với `B`. Nhưng đối tượng hiện tại là `A1` và không triển khai `B`, nên cast thất bại lúc chạy.

**Bài 5.** Vì sao thay `someA` bằng biến kiểu tĩnh `A1` có thể làm kết quả kiểm tra cast thay đổi?

**Đáp án:** `A1` là record, ngầm định `final`. Không còn lớp con nào của `A1` để bổ sung `B`. Vì thế, nếu bản thân `A1` không triển khai `B`, cặp kiểu đó disjoint ngay ở bước kiểm tra tĩnh.

**Bài 6.** `JobResult value = null;` có cho phép cast sang `UnrelatedRecord` không, nếu cả hai kiểu đã disjoint?

**Đáp án:** Không. Kết luận về tính hợp lệ của phép cast được đưa ra từ kiểu tĩnh `JobResult` và `UnrelatedRecord`. Nếu dùng `Object value = null;`, cast sang `UnrelatedRecord` có thể hợp lệ và kết quả là `null`.

## 15. Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): phần **Narrowing Reference Conversion and Disjoint Types** giải thích trường hợp cast bất khả thi và ví dụ `sealed`/`non-sealed`.
- [Java Language Specification 17 — `5.1.6 Narrowing Reference Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): định nghĩa phép chuyển tham chiếu thu hẹp, quy tắc các kiểu disjoint và kiểm tra runtime.
- [Java Language Specification 17 — `5.5 Casting Contexts`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): ngữ cảnh ép kiểu và điều kiện hợp lệ.
- [Java Language Specification 17 — `15.16 Cast Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.16): quy tắc biểu thức cast.
- [Java Language Specification 17 — `15.20.2 The instanceof Operator`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): `instanceof` thông thường và pattern matching.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục đích và thiết kế chính thức của `sealed` trong Java 17.

**Điểm cốt lõi:** `sealed` không làm Java bỏ kiểm tra kiểu tại runtime. Nó làm **kiểm tra tĩnh chính xác hơn**, giúp `javac` loại những phép ép kiểu không thể có đối tượng chung. Khi phân cấp vẫn có nhánh mở hoặc có kiểu triển khai chung, cast có thể được chấp nhận và chương trình vẫn phải xử lý trường hợp đối tượng runtime không đúng kiểu.
