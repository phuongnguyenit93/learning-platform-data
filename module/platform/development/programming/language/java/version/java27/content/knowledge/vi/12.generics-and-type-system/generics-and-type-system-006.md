# Raw type, unchecked warning và heap pollution trong Java

**Generics** giúp Java phát hiện nhiều lỗi trộn kiểu ngay khi biên dịch. Tuy nhiên, hệ thống generic hiện hành vẫn hỗ trợ một số thao tác mà compiler không thể xác minh hoàn toàn, đặc biệt khi dùng **raw type**, ép kiểu generic và **varargs với kiểu không reifiable**. Những thao tác này thường sinh ra **unchecked warning**; khi cấu trúc dữ liệu thực tế không còn đáp ứng kiểu được khai báo, chương trình rơi vào tình trạng **heap pollution**.

Bài viết thuộc chương **Generics và hệ thống kiểu** của nội dung học **Java 27 và các kiến thức liên quan**. Các quy tắc được trình bày là các quy tắc Java đang được áp dụng chính thức, không dựa vào tính năng preview. Raw type vẫn là một phần của ngôn ngữ để duy trì khả năng tương tác với API chưa khai báo type argument, nhưng **không phải lựa chọn nên dùng khi thiết kế mã generic mới**.

Sau bài học, bạn có thể:

- Nhận diện raw type và hiểu tại sao nó làm giảm độ an toàn kiểu.
- Phân biệt `rawtypes` warning, unchecked call, unchecked conversion và unchecked cast.
- Giải thích heap pollution xảy ra khi nào, và vì sao lỗi `ClassCastException` đôi khi xuất hiện rất xa nơi gây lỗi.
- Hiểu vai trò của **type erasure**, kiểu **reifiable** và generic varargs.
- Dùng `List<?>`, wildcard có ràng buộc, kiểm tra phần tử runtime và `@SafeVarargs` đúng trường hợp.
- Xử lý cảnh báo có căn cứ, thay vì che chúng bằng `@SuppressWarnings` trên phạm vi lớn.

## 1. Generics bảo vệ chúng ta khỏi điều gì?

Xét một danh sách tên người dùng:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");

// names.add(42); // Lỗi biên dịch: Integer không phải String.
```

Khai báo `List<String>` thể hiện hợp đồng: phần tử được truy cập qua API generic này có kiểu `String`. Compiler sử dụng type argument `String` để kiểm tra lời gọi `add`, kiểu nhận được khi `get` và các phép gán liên quan.

```java
String first = names.get(0); // Không cần ép kiểu tường minh.
```

Điểm quan trọng: sự an toàn kiểu của generics được thực thi chủ yếu bằng **kiểm tra tĩnh khi biên dịch**. Java không tạo một loại `ArrayList<String>` độc lập ở runtime cho từng type argument. Điều này liên quan trực tiếp đến type erasure.

## 2. Type erasure: nền tảng để hiểu raw type

Java generics sử dụng **type erasure**. Đối với các lớp và phương thức generic thông thường, compiler dùng thông tin kiểu khi kiểm tra mã nguồn rồi xóa/thay thế nhiều tham số kiểu trong biểu diễn runtime. Ví dụ, type variable không có bound đặc biệt thường được thay bằng `Object`; type variable có bound được thay bằng erasure của bound phù hợp.

Mô hình đơn giản:

```java
class Box<T> {
    private T value;

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Ở cấp độ biểu diễn đã erasure, chữ ký của một số thành phần có dạng tương tự:

```java
// Minh họa về erasure, không phải mã nguồn Java được sinh nguyên văn.
class Box {
    private Object value;

    void set(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Compiler có thể đưa các phép cast cần thiết vào vị trí sử dụng. Trong trường hợp phù hợp, nó cũng có thể sinh *bridge methods* để bảo toàn đa hình sau erasure.

### 2.1. Runtime không biết phần tử của một List được khai báo là String hay Integer

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(words.getClass() == numbers.getClass()); // true
```

Cả hai đều là instance của cùng class `ArrayList`. Từ một đối tượng `List` bất kỳ, JVM không có bằng chứng đáng tin cậy rằng mọi phần tử của nó là `String` chỉ nhờ tham số kiểu xuất hiện trong khai báo biến ở mã nguồn.

**Lưu ý:** một số thông tin generic về khai báo class, field hoặc method vẫn có thể được lưu trong metadata và đọc qua reflection. Điều đó không có nghĩa mỗi instance mang một type argument có thể dùng để chứng minh toàn bộ nội dung collection ở runtime.

### 2.2. Kiểu reifiable và non-reifiable

*Reifiable type* là kiểu có đủ thông tin để biểu diễn/kiểm tra tại runtime theo quy tắc Java. Một số ví dụ:

| Kiểu | Reifiable? | Giải thích |
|---|---|---|
| `String` | Có | Class không generic |
| `int` | Có | Kiểu nguyên thủy |
| `List` | Có | Raw type |
| `List<?>` | Có | Các type argument đều là unbounded wildcard |
| `List<String>` | Không | Type argument `String` không được reify |
| `List<? extends Number>` | Không | Wildcard có ràng buộc, không phải wildcard không giới hạn |
| `T` trong `class Box<T>` | Không | Type variable |
| `String[]` | Có | Mảng có component type reifiable |
| `List<String>[]` | Không | Component type không reifiable |

Vì vậy:

```java
static boolean isSomeList(Object value) {
    return value instanceof List<?>; // Hợp lệ.
}

// Không hợp lệ:
// if (value instanceof List<String>) { ... }
```

Một phép `instanceof List<String>` không thể xác minh chính xác type argument ở runtime. Dùng `List<?>` khi chỉ cần biết giá trị là một danh sách, rồi kiểm tra từng phần tử nếu cần.

## 3. Raw type là gì?

**Raw type** là cách sử dụng tên một kiểu generic **mà không cung cấp danh sách type argument**. Ví dụ:

```java
List rawList = new ArrayList<String>(); // Raw List.
Box rawBox = new Box<Integer>();        // Raw Box.
```

Đối chiếu:

```java
List<String> strings = new ArrayList<>(); // Parameterized type.
List<?> unknown = strings;                // Parameterized type với wildcard.
List raw = strings;                       // Raw type.
```

`List<?>` **không phải** raw type. Nó vẫn tham gia kiểm tra generic, chỉ không công bố kiểu phần tử cụ thể ở nơi tham chiếu. Đây là sự khác biệt quan trọng.

Raw type được Java cho phép để hỗ trợ tương tác với những khai báo và thư viện không cung cấp đủ thông tin generic. Nhưng khi dùng raw type, nhiều kiểm tra quan trọng của compiler bị bỏ qua hoặc chỉ còn là cảnh báo.

### 3.1. Ví dụ raw type làm mất an toàn kiểu

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List raw = names;        // Raw alias trỏ cùng đối tượng.
raw.add(42);            // Unchecked call warning.
String name = names.get(0); // Có thể ném ClassCastException.
```

Mặc dù `names` có kiểu `List<String>`, một biến raw khác vẫn có thể tham chiếu cùng danh sách và thêm `Integer` vào đó.

Compiler có thể cảnh báo ở `raw.add(42)`; nó không nhất thiết tạo lỗi biên dịch. Cảnh báo này có giá trị vì phép gọi không còn được kiểm tra tương thích với `String` theo hợp đồng của danh sách.

### 3.2. Raw type không có nghĩa Object là type argument được khai báo

Hai khai báo sau khác nhau về ngữ nghĩa:

```java
List raw = new ArrayList<String>();
List<Object> objects = new ArrayList<>();
```

`List<Object>` thực sự có type argument `Object`. Compiler kiểm tra thao tác của nó theo `List<Object>`. Raw `List` bỏ thông tin type argument và có thể đưa tới unchecked operation khi dùng những method có chữ ký phụ thuộc vào tham số kiểu.

Cũng không nên nhầm `List<Object>` với `List<?>`:

```java
List<String> strings = List.of("Java");
List<?> view = strings;    // Hợp lệ.

// List<Object> values = strings; // Không hợp lệ: generics bất biến theo type argument.
```

`List<String>` không phải subtype của `List<Object>`, dù `String` là subtype của `Object`.

## 4. Unchecked warning là gì?

*Unchecked warning* là cảnh báo khi compiler cho phép một thao tác để duy trì khả năng tương thích, nhưng không thể kiểm chứng đầy đủ rằng ràng buộc generic được đáp ứng.

Nó khác với lỗi biên dịch thông thường: mã có thể vẫn được sinh ra và chạy. Tuy nhiên, **một cảnh báo unchecked không nên bị xem là vô hại chỉ vì chương trình có thể chạy ở vài trường hợp thử nghiệm**.

Các trường hợp phổ biến:

| Tình huống | Ví dụ | Rủi ro |
|---|---|---|
| Unchecked call | `raw.add(42)` | Ghi giá trị không phù hợp vào đối tượng được dùng như generic collection |
| Unchecked conversion | `List<String> xs = raw` | Gắn hợp đồng `String` cho tham chiếu chưa được xác minh |
| Unchecked cast | `(List<String>) object` khi runtime chỉ xác minh được kiểu thô | Cast có thể thành công nhưng phần tử bên trong không đúng `String` |
| Non-reifiable varargs | `method(List<String>... groups)` | Có thể tạo mảng không reifiable và phát sinh alias không an toàn |
| Raw type lint | `List raw` | Mất type argument; thường được báo qua `-Xlint:rawtypes` |

**Lưu ý phân biệt:** cảnh báo `rawtypes` không đồng nhất với cảnh báo `unchecked`. Một khai báo raw có thể được `-Xlint:rawtypes` nhắc tới mà chưa gây một unchecked call cụ thể; việc gán hay gọi method sau đó mới phát sinh `unchecked`.

### 4.1. Xem cảnh báo chi tiết khi biên dịch

Với `javac`, có thể yêu cầu hiển thị cảnh báo rõ ràng:

```bash
javac -Xlint:unchecked -Xlint:rawtypes GenericsWarningsDemo.java
```

Hoặc:

```bash
javac -Xlint:all GenericsWarningsDemo.java
```

`-Xlint:unchecked` tập trung vào thao tác generic không được kiểm tra đầy đủ, còn `-Xlint:rawtypes` giúp phát hiện khai báo/sử dụng raw type. Tùy cấu hình, compiler có thể chỉ in ghi chú yêu cầu bật `-Xlint:unchecked` thay vì hiển thị chi tiết ngay.

Cảnh báo và dòng chẩn đoán cụ thể có thể khác nhau đôi chút giữa phiên bản compiler và ngữ cảnh mã. Điều quan trọng là xác định **phép toán nào** tạo cảnh báo và **hợp đồng kiểu nào** không thể được chứng minh.

## 5. Unchecked call: gọi method thông qua raw reference

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class UncheckedCallExample {
    static void demo() {
        List<String> names = new ArrayList<>();
        List raw = names;
        raw.add(99);     // Unchecked call to add(E).
    }
}
```

Chữ ký tổng quát của `List<E>.add(E)` phụ thuộc vào `E`. Khi dùng raw `List`, thông tin `E` không được cung cấp nên compiler không thể kiểm tra đối số `99` có đúng kiểu phần tử thực tế hay không.

Điều nguy hiểm không chỉ nằm ở `99`; raw alias có thể được truyền qua nhiều method, từ đó làm cho dữ liệu sai kiểu xuất hiện rất xa vị trí ghi.

Một nguyên tắc thực tế là **không để raw reference có quyền ghi vào collection generic** nếu có thể tránh được.

## 6. Unchecked conversion: đưa raw reference về kiểu tham số hóa

Ví dụ:

```java
List raw = new ArrayList<Integer>();
raw.add(10);

List<String> names = raw; // Unchecked conversion warning.
```

Đây là phép chuyển từ kiểu `List` sang `List<String>`, trong khi runtime không có cơ chế xác minh tổng quát rằng danh sách thực sự chỉ chứa `String`.

Giả sử tiếp tục:

```java
String first = names.get(0); // ClassCastException tại đây.
```

Một danh sách chứa `Integer` đã được đối xử như `List<String>`. **Heap pollution xảy ra trước thời điểm đọc gây lỗi**: phép gán unchecked đã đưa tham chiếu vào trạng thái không phù hợp với kiểu generic của biến.

### 6.1. Vì sao lỗi đôi khi xuất hiện muộn?

Ở thời điểm gán `names = raw`, JVM thường chỉ cần biết đối tượng có phải một `List` hay không. Nó không thể kiểm tra `List<String>` bằng cách xác thực type argument từ đối tượng.

Khi `names.get(0)` được sử dụng trong ngữ cảnh yêu cầu `String`, compiler có thể sinh phép cast thích hợp. Nếu phần tử thực tế là `Integer`, phép cast thất bại và ném `ClassCastException`.

Do đó:

```text
Raw/unchecked operation
        |
        v
Tham chiếu generic không còn đúng hợp đồng
        |
        v
Chương trình có thể chạy tiếp một thời gian
        |
        v
Đọc phần tử với kiểu cụ thể
        |
        v
ClassCastException
```

Việc log lỗi chỉ ghi nhận `get(0)` là chưa đủ để tìm nguyên nhân. Cần truy ngược đường đi của tham chiếu và những phép ghi/cast unchecked trước đó.

## 7. Unchecked cast: ép kiểu không chứng minh được nội dung

Ép một đối tượng thành `List<String>` khác với ép nó thành `String`.

```java
Object source = new ArrayList<Integer>(List.of(1, 2, 3));

// Chỉ dùng để minh họa hành vi nguy hiểm:
@SuppressWarnings("unchecked")
List<String> strings = (List<String>) source;

String first = strings.get(0); // ClassCastException.
```

Chính cast `(List<String>) source` có thể chạy qua vì runtime xác minh được đối tượng là `List`, chứ không thể khẳng định mọi phần tử là `String`. Trong ví dụ, `@SuppressWarnings("unchecked")` **chỉ ẩn cảnh báo**; nó không tạo ra bất kỳ phép kiểm tra kiểu bổ sung nào.

**Không nên sao chép cách tắt warning này vào production**. Nó được đặt ở ví dụ chỉ để cho thấy một cast unchecked vẫn có thể làm chương trình thất bại khi sử dụng dữ liệu.

### 7.1. Kiểm tra phần tử thay vì tin vào unchecked cast

Khi tiếp nhận dữ liệu không rõ kiểu, chuyển sang collection mới và xác minh từng phần tử:

```java
import java.util.ArrayList;
import java.util.List;

static <T> List<T> checkedCopy(Iterable<?> source, Class<T> elementType) {
    List<T> result = new ArrayList<>();
    for (Object item : source) {
        result.add(elementType.cast(item));
    }
    return result;
}
```

Dùng:

```java
List<?> incoming = List.of("An", "Bình");
List<String> names = checkedCopy(incoming, String.class);
```

Nếu `incoming` chứa `Integer`, `elementType.cast(item)` ném `ClassCastException` **ở ranh giới chuyển đổi**, thay vì để dữ liệu sai kiểu tiếp tục lan truyền qua hệ thống.

Lưu ý `Class.cast(null)` trả về `null`. Nếu hợp đồng không chấp nhận phần tử null, bổ sung `Objects.requireNonNull(item)` hoặc kiểm tra tường minh.

### 7.2. Class<T> không giải quyết được mọi kiểu generic lồng nhau

Không thể có một `List<String>.class` trong Java theo nghĩa tương tự `String.class`. Vì type argument không được reify đầy đủ, `Class<T>` thường phù hợp nhất để kiểm tra kiểu phần tử trực tiếp như `String`, `Integer` hoặc một class cụ thể.

Với `List<List<String>>`, cần kiểm tra cả danh sách ngoài, các danh sách con và từng phần tử bằng logic phù hợp; một phép `List.class.cast(...)` không chứng minh cấu trúc generic lồng nhau đúng kiểu.

## 8. Heap pollution: định nghĩa và cơ chế

Theo Java Language Specification, **heap pollution** xảy ra khi một biến có kiểu tham số hóa tham chiếu đến một đối tượng không thực sự phù hợp với kiểu tham số hóa đó.

Ví dụ:

```java
List<Integer> source = new ArrayList<>();
source.add(1);

List raw = source;
List<String> target = raw; // Unchecked conversion.
```

`target` được khai báo là `List<String>` nhưng đang tham chiếu đến danh sách được xây dựng và sử dụng như `List<Integer>`. Khi đưa `target` vào một API kỳ vọng `List<String>`, bất biến kiểu đã bị phá vỡ.

### 8.1. Heap pollution và ClassCastException không phải một

- **Heap pollution** là trạng thái vi phạm hợp đồng kiểu generic.
- **ClassCastException** là một hậu quả runtime có thể quan sát được khi chương trình cố dùng một giá trị như kiểu không đúng.

Heap pollution **có thể tồn tại mà chưa ném exception**, ví dụ danh sách sai kiểu chưa từng được đọc ở ngữ cảnh yêu cầu `String`.

Ngược lại, `ClassCastException` có thể xảy ra với phép ép kiểu bình thường, không nhất thiết có heap pollution:

```java
Object number = 42;
// String text = (String) number; // Ném ClassCastException, không cần generics.
```

Đừng đồng nhất mọi `ClassCastException` với heap pollution.

### 8.2. Có unchecked warning chưa chắc đã có heap pollution

Cảnh báo báo **nguy cơ không thể chứng minh an toàn**, không khẳng định chắc chắn có dữ liệu sai kiểu.

```java
List raw = new ArrayList<String>();
raw.add("An");

List<String> names = raw; // Unchecked conversion.
```

Nếu danh sách thực tế chỉ chứa `String` trong toàn bộ thời gian sử dụng, đoạn mã có thể vẫn hoạt động như dự kiến, dù compiler không thể chứng minh điều đó.

Vì vậy, khi phải tiếp nhận API có raw type, cần đánh giá dựa trên **bằng chứng về dữ liệu và quyền ghi**, không chỉ dựa trên thực tế rằng một lần chạy không lỗi.

### 8.3. Không thấy warning không có nghĩa chắc chắn an toàn

Một build có thể không hiển thị cảnh báo vì:

- Chưa bật tùy chọn chẩn đoán thích hợp.
- Cảnh báo bị ẩn bằng `@SuppressWarnings`.
- Một số binary được biên dịch riêng bằng compiler khác hoặc từ mã nguồn cũ.
- Việc alias mảng kiểu không reifiable tạo rủi ro mà thao tác ghi cụ thể không có warning tương ứng.

Vì thế, mục tiêu là **loại bỏ nguyên nhân và giữ hợp đồng kiểu**, không phải đơn thuần khiến màn hình build không còn dòng cảnh báo.

## 9. Raw type khác wildcard như thế nào?

Wildcards là một phần của hệ thống generic hiện hành, cho phép diễn đạt kiểu dữ liệu linh hoạt mà vẫn giữ kiểm tra tĩnh.

### 9.1. List<?>: danh sách có kiểu phần tử chưa biết

```java
List<String> strings = new ArrayList<>(List.of("A", "B"));
List<?> unknown = strings;

Object first = unknown.get(0); // Đọc an toàn dưới dạng Object.

// unknown.add(42);    // Lỗi biên dịch.
// unknown.add("C");   // Cũng lỗi biên dịch.
unknown.add(null);     // Được phép về mặt kiểu.
```

Vì compiler không biết type argument của `unknown`, nó không cho thêm đối tượng khác `null` vào danh sách theo cách có thể làm sai kiểu phần tử.

So sánh:

```java
List raw = strings;
raw.add(42); // Có thể biên dịch với unchecked warning.
```

**Khi chỉ cần đọc hoặc duyệt một danh sách mà không biết kiểu phần tử, `List<?>` thường phù hợp hơn raw `List`.**

### 9.2. ? extends T và ? super T

Các giới hạn wildcard có thể mô tả API linh hoạt, tránh ép kiểu không được kiểm tra:

```java
static double sum(List<? extends Number> numbers) {
    double total = 0;
    for (Number n : numbers) {
        total += n.doubleValue();
    }
    return total;
}

static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

- `? extends Number`: có thể **đọc** phần tử như `Number`; thường không được thêm giá trị cụ thể vì chưa biết subtype chính xác.
- `? super Integer`: có thể **ghi** `Integer`; đọc ra thường chỉ được bảo đảm kiểu `Object`.

Quy tắc gợi nhớ **PECS** (*Producer Extends, Consumer Super*) hữu ích trong nhiều API collection. Nhưng luôn đọc hợp đồng thật: wildcard không thay thế được việc xác minh dữ liệu từ một nguồn không đáng tin cậy.

### 9.3. Dấu <> (diamond) không biến raw type thành generic

```java
List<String> names = new ArrayList<>(); // Generic, compiler suy ra String.
List raw = new ArrayList<>();           // Biến vẫn là raw List.
```

Dấu `<>` ở biểu thức tạo object yêu cầu suy luận type argument cho constructor/class; nó **không sửa được** việc biến bên trái được khai báo bằng raw type.

## 10. Mảng Java và generic: vì sao nguy hiểm?

Mảng có kiểm tra **component type ở runtime**. Ví dụ:

```java
String[] names = new String[1];
Object[] objects = names;

// objects[0] = 123; // Ném ArrayStoreException ở runtime.
```

Runtime biết mảng thực tế có component type `String`, nên phát hiện việc cố ghi `Integer`.

Với generics, thông tin `String` trong `List<String>` không được reify tương tự:

```java
// Không hợp lệ: generic array creation.
// List<String>[] groups = new List<String>[2];
```

Tạo trực tiếp mảng có component type tham số hóa không reifiable như trên bị cấm. Nếu cho phép tự do, mã có thể lợi dụng alias `Object[]` để đưa danh sách với type argument khác vào mảng, trong khi runtime không kiểm tra được generic argument.

### 10.1. Mảng List<?> có thể hợp lệ

```java
List<?>[] groups = new List<?>[2];

groups[0] = List.of("Java");
groups[1] = List.of(42);
```

`List<?>` là reifiable, nên có thể làm component type của mảng theo quy tắc ngôn ngữ. Nhưng điều đó không cho phép biến `groups[0]` thành `List<String>` mà không kiểm tra.

Với nhu cầu lưu nhiều collection có cùng kiểu generic, một `List<List<T>>` thường rõ ràng và an toàn hơn so với mảng `List<T>[]`.

## 11. Varargs với kiểu non-reifiable có thể gây heap pollution

Tham số varargs như `String... args` được xử lý thông qua một mảng. Với kiểu phần tử không reifiable như `List<String>`, việc tạo mảng phù hợp ở runtime trở nên nhạy cảm.

Ví dụ dưới đây **cố tình không an toàn** để minh họa lỗi:

```java
import java.util.List;

class DangerousVarargs {
    static void breakTypes(List<String>... groups) {
        Object[] objects = groups;
        objects[0] = List.of(42); // Runtime chỉ kiểm tra được List.
        String text = groups[0].get(0); // ClassCastException.
        System.out.println(text);
    }

    static void demo() {
        breakTypes(List.of("A"), List.of("B"));
    }
}
```

Luồng xảy ra:

1. Lời gọi varargs cần truyền dữ liệu dưới dạng mảng.
2. Ở runtime, mảng có component type thể hiện được là `List`, không giữ ràng buộc `List<String>`.
3. `Object[] objects = groups` tạo **alias** trỏ cùng mảng.
4. Gán `List.of(42)` vào `objects[0]` không bị kiểm tra type argument của danh sách.
5. Phần tử `groups[0]` giờ là `List<Integer>`, dù biến mảng được khai báo là `List<String>[]`.
6. `groups[0].get(0)` trong ngữ cảnh `String` gây `ClassCastException`.

Đây là một ví dụ **heap pollution qua mảng non-reifiable**. Compiler có thể cảnh báo về varargs có kiểu phần tử non-reifiable và tại lời gọi tạo mảng generic. Thao tác gán qua `Object[]` trong thân method có thể không sinh unchecked warning riêng.

### 11.1. Cảnh báo generic varargs có ý nghĩa gì?

```java
static void process(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Bản thân cách duyệt trên có thể là an toàn nếu method không sửa hoặc tiết lộ mảng varargs; tuy nhiên compiler vẫn cần cảnh báo vì **chữ ký cho phép** hình thành mảng non-reifiable ở lời gọi.

Cảnh báo không có nghĩa mọi method generic varargs đều làm hỏng kiểu; nó nhắc tác giả phải kiểm chứng cách method xử lý mảng và dữ liệu nhận vào.

## 12. Dùng @SafeVarargs đúng mục đích

`@SafeVarargs` là lời **cam kết có trách nhiệm của tác giả** rằng method hoặc constructor không thực hiện thao tác không an toàn với tham số varargs non-reifiable.

Nó có thể loại bỏ unchecked warning tại khai báo varargs và tại các lời gọi liên quan. **Annotation không làm phép toán không an toàn trở nên an toàn ở runtime.**

### 12.1. Ví dụ method varargs thực sự an toàn

```java
import java.util.ArrayList;
import java.util.List;

class Lists {
    @SafeVarargs
    static <T> List<T> concatenate(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return result;
    }
}
```

Method này:

- Chỉ **đọc** các phần tử mảng `groups`.
- Không ghi một `List` không phù hợp vào phần tử của mảng.
- Không trả về hoặc lưu mảng varargs vào nơi khác, tránh lộ alias để bên ngoài sửa nội dung mảng.
- Sao chép **các phần tử danh sách** vào một `ArrayList<T>` mới theo kiểm tra generic của compiler.

Ví dụ sử dụng:

```java
List<String> all = Lists.concatenate(
        List.of("Java", "SQL"),
        List.of("HTTP")
);
System.out.println(all); // [Java, SQL, HTTP]
```

`List<? extends T>` cho phép việc đọc phần tử mà không cần unchecked cast. Vì method không để lộ mảng varargs nên người gọi không thể thay phần tử mảng thông qua một alias do method trả về.

### 12.2. Không dùng annotation để che một method nguy hiểm

```java
// KHÔNG ĐƯỢC gắn @SafeVarargs: thân method không an toàn.
static void corrupt(List<String>... groups) {
    Object[] sameArray = groups;
    sameArray[0] = List.of(123);
}
```

Nếu thêm `@SafeVarargs`, compiler có thể bớt cảnh báo ở nơi gọi, nhưng dữ liệu vẫn có thể bị làm sai kiểu. Đây là **cam kết sai**, không phải cách sửa lỗi.

### 12.3. Khi nào được phép đặt @SafeVarargs?

Theo quy tắc ngôn ngữ Java hiện hành, annotation này chỉ được đặt trên:

- Method varargs `static`.
- Method varargs `final`.
- Method varargs `private`.
- Constructor có tham số varargs.

Không được dùng trên method không phải varargs, hoặc một instance method có thể bị override mà không thuộc những trường hợp được cho phép. Với varargs có kiểu phần tử reifiable như `String...` hoặc `int...`, annotation thường không cần thiết và compiler có thể cảnh báo rằng nó dư thừa.

Ngay cả khi cú pháp hợp lệ, tác giả vẫn phải chứng minh thân method không dẫn đến hành vi không an toàn với varargs.

## 13. @SuppressWarnings("unchecked") có sửa lỗi không?

**Không.** `@SuppressWarnings` chỉ yêu cầu compiler không báo một số loại cảnh báo trong phạm vi khai báo được đánh dấu. Nó không xác minh dữ liệu, không thay đổi erasure và không ngăn `ClassCastException`.

Ví dụ nguy hiểm:

```java
@SuppressWarnings("unchecked")
static List<String> unsafe(Object source) {
    return (List<String>) source;
}
```

Method này không kiểm tra phần tử. Nếu `source` là `List<Integer>`, method vẫn có thể trả về một tham chiếu khai báo là `List<String>`.

### 13.1. Khi không tránh được unchecked cast

Có những API hoặc cấu trúc nội bộ cần thao tác mà compiler không thể chứng minh, dù tác giả có bằng chứng an toàn (ví dụ một số kiểu mảng tạo bằng reflection với runtime component type đã được kiểm soát).

Khi việc này thực sự cần thiết:

1. Tìm giải pháp không cần unchecked cast trước.
2. Xác định **bất biến** khiến cast được cho là an toàn.
3. Viết kiểm tra runtime nếu có thể.
4. Giới hạn `@SuppressWarnings("unchecked")` ngay tại method hoặc biến cục bộ tối thiểu.
5. Giải thích lý do trong comment và bảo vệ bằng test, nhất là test kiểu sai và test giá trị biên.

Ví dụ minh họa phép tạo mảng qua reflection:

```java
import java.lang.reflect.Array;

static <T> T[] newTypedArray(Class<T> componentType, int size) {
    if (componentType.isPrimitive()) {
        throw new IllegalArgumentException("Require a reference component type");
    }
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(componentType, size);
    return result;
}
```

Giải thích: `Array.newInstance(componentType, size)` tạo mảng có **runtime component type đúng bằng `componentType`**, nên cast được hỗ trợ bằng bất biến có thể kiểm tra. Đây là trường hợp dành cho `Class<T>` đại diện cho loại component type có thể được reify; không nên suy rộng kỹ thuật này thành cách "tạo `List<String>[]` an toàn" bằng cách bỏ qua type erasure.

### 13.2. Phân biệt suppress rawtypes và unchecked

```java
@SuppressWarnings("rawtypes")
static void exampleDeclaration() {
    List raw = new ArrayList();
}
```

`rawtypes` nhắm vào việc dùng raw type; `unchecked` nhắm vào thao tác không được kiểm tra đầy đủ. Hai nhóm cảnh báo khác nhau. Thêm `@SuppressWarnings({"rawtypes", "unchecked"})` lên cả class chỉ để có build "sạch" thường che giấu nhiều vấn đề hơn là giải quyết.

**Nguyên tắc:** chẩn đoán từng warning và loại bỏ nguyên nhân ở biên API trước; suppression chỉ là lựa chọn có điều kiện cuối cùng.

## 14. Thiết kế API để tránh raw type

### 14.1. Khai báo type parameter trên method

Thay vì API trả về raw collection:

```java
// Tránh thiết kế mới kiểu này:
static List getItems() {
    return new ArrayList();
}
```

Dùng kiểu cụ thể khi biết phần tử:

```java
static List<String> getNames() {
    return List.of("An", "Bình");
}
```

Hoặc dùng method generic khi kiểu kết quả thực sự phụ thuộc vào đầu vào:

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
```

Lưu ý `List.of` không nhận phần tử `null`. Nếu cần hỗ trợ null theo hợp đồng, hãy chọn cấu trúc và cách tạo dữ liệu tương ứng.

### 14.2. Dùng wildcard khi chưa biết type argument

```java
static void printAll(Iterable<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Method không cần biết kiểu phần tử, nên `Iterable<?>` diễn đạt ý định tốt hơn raw `Iterable`.

Nếu chỉ cần kiểm tra size của một collection:

```java
static int sizeOf(List<?> items) {
    return items.size();
}
```

Không có lý do để sử dụng raw `List`.

### 14.3. Dùng generic type constraint khi cần quan hệ giữa các tham số

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> destination
) {
    destination.addAll(source);
}
```

Ở đây compiler biết rằng mọi phần tử đọc từ `source` đều phù hợp để ghi vào `destination`, không cần cast hoặc raw alias.

Mục tiêu của generics là **diễn đạt mối quan hệ kiểu trong chữ ký** để compiler kiểm tra thay chúng ta.

## 15. Tích hợp với API raw type hiện có

Một số hệ thống cần tương tác với API cũ hoặc phần mở rộng không còn thông tin generic. Đây là trường hợp raw type vẫn có ý nghĩa về khả năng tương thích.

Giả sử nhận một danh sách từ API chưa khai báo type argument:

```java
// Mô tả một nguồn bên ngoài trả về kiểu raw:
// List result = legacyClient.loadItems();
```

**Không nên** truyền trực tiếp raw result qua toàn bộ ứng dụng dưới dạng `List<String>` bằng unchecked cast. Thay vào đó, đặt một **adapter có kiểm tra kiểu tại biên**:

```java
static List<String> toStrings(List<?> input) {
    List<String> result = new ArrayList<>();

    for (Object element : input) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException(
                    "Unexpected element: " + element
            );
        }
        result.add(text);
    }

    return List.copyOf(result);
}
```

Method trên chỉ chấp nhận các phần tử thực sự là `String` khác null, sao chép thành danh sách mới và trả về danh sách không cho phép sửa cấu trúc. Nếu `input` chứa sai kiểu hoặc null, method từ chối ngay tại ranh giới.

Bản `toStrings` không cần cast unchecked, vì pattern `instanceof String text` xác minh từng phần tử ở runtime.

### 15.1. Tại sao phải sao chép?

Nếu cùng trả về một alias của danh sách raw có thể sửa, mã khác vẫn có thể thêm phần tử sai kiểu **sau** khi adapter xác minh. Sao chép dữ liệu tạo một biên bảo vệ rõ ràng và ngăn việc thay đổi cấu trúc của collection gốc làm hỏng collection trả về.

Tuy nhiên, **bản sao danh sách không làm các phần tử bên trong bất biến**. Nếu phần tử là đối tượng mutable, trạng thái của chúng vẫn có thể thay đổi; hợp đồng cần xác định rõ yêu cầu về deep copy hay immutability.

### 15.2. Collections.checkedList có ích ở đâu?

`Collections.checkedList(list, String.class)` trả một view có kiểm tra kiểu runtime đối với những thao tác ghi đi qua view đó:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>();
List<String> guarded = Collections.checkedList(backing, String.class);

guarded.add("Java");
```

View này hữu ích khi phải chia sẻ collection với mã có thể truy cập qua raw reference. Nhưng nó **không bảo vệ tuyệt đối** nếu mã khác giữ một alias của `backing` và sửa trực tiếp danh sách gốc, bỏ qua view.

Một `checkedList` cũng không biến một danh sách đã chứa sai kiểu thành danh sách đúng kiểu theo phép kiểm tra toàn bộ; cần xác minh dữ liệu đầu vào riêng nếu có rủi ro heap pollution trước đó.

## 16. Ví dụ hoàn chỉnh: code an toàn, không cần unchecked cast

Lưu đoạn sau thành file `GenericsSafetyDemo.java`. Nó kết hợp việc xác minh runtime ở ranh giới và `@SafeVarargs` cho method thực sự chỉ đọc mảng varargs.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericsSafetyDemo {

    public static <T> List<T> checkedCopy(
            Iterable<?> source,
            Class<T> elementType
    ) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(elementType, "elementType");

        List<T> result = new ArrayList<>();

        for (Object element : source) {
            result.add(Objects.requireNonNull(
                    elementType.cast(element),
                    "element"
            ));
        }

        return result;
    }

    @SafeVarargs
    public static <T> List<T> concatenate(
            List<? extends T>... groups
    ) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(Objects.requireNonNull(group, "group"));
        }

        return result;
    }

    public static void main(String[] args) {
        List<?> inbound = List.of("An", "Bình");
        List<String> names = checkedCopy(inbound, String.class);

        List<String> combined = concatenate(
                names,
                List.of("Chi")
        );

        System.out.println(combined);

        try {
            checkedCopy(List.of("An", 42), String.class);
        } catch (ClassCastException exception) {
            System.out.println("Invalid element type");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:unchecked -Xlint:rawtypes GenericsSafetyDemo.java
java GenericsSafetyDemo
```

Kết quả dự kiến:

```text
[An, Bình, Chi]
Invalid element type
```

### 16.1. Vì sao chương trình này không cần raw type?

- `Iterable<?>` chấp nhận dữ liệu có kiểu phần tử chưa biết, nhưng chỉ cho đọc thành `Object`.
- `Class<T>.cast` kiểm tra kiểu ở thời điểm chuyển đổi sang danh sách `List<T>`.
- `concatenate` dùng wildcard `? extends T` để đọc từ nhiều danh sách có kiểu tương thích.
- Mảng varargs không bị ghi đè và không được trả về hoặc lưu giữ dưới dạng alias.
- `@SafeVarargs` là cam kết có căn cứ về hành vi của method, không phải cách giấu lỗi.
- Các bước biến đổi đặt lỗi sai kiểu tại đầu vào, giúp xác định nguyên nhân nhanh hơn.

### 16.2. Vì sao kết quả mới là List mutable?

Method `checkedCopy` và `concatenate` trả về `ArrayList` mới. Chúng không hứa tính bất biến; việc ai được phép sửa danh sách trả về là một phần cần cân nhắc khi thiết kế API.

Nếu muốn trả `List` không cho sửa cấu trúc, có thể dùng `List.copyOf(result)` **khi đã bảo đảm các phần tử không null**; `List.copyOf` không chấp nhận null. Với đối tượng phần tử mutable, danh sách không cho sửa cấu trúc vẫn không bảo đảm deep immutability.

## 17. Ví dụ cố tình không an toàn: cảnh báo nằm xa lỗi

Để đối chiếu, chương trình sau có thể biên dịch nhưng **không phải code nên sử dụng trong hệ thống thực tế**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeFailureDemo {

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();

        List raw = names;
        raw.add(42); // Unchecked call warning.

        try {
            String name = names.get(0);
            System.out.println(name);
        } catch (ClassCastException exception) {
            System.out.println("Detected invalid element at read time");
        }
    }
}
```

Kết quả dự kiến:

```text
Detected invalid element at read time
```

Dòng gây sai hợp đồng là `raw.add(42)`; dòng phát hiện lỗi là `names.get(0)`. Chúng có thể nằm ở các class và tầng ứng dụng khác nhau. Vì vậy, khi xử lý `ClassCastException` liên quan đến collection generic, luôn tìm các thao tác:

- Gán từ raw type sang parameterized type.
- Ép kiểu sang generic collection mà không xác minh phần tử.
- Ghi phần tử qua raw alias.
- Tạo hoặc chia sẻ mảng varargs với non-reifiable element type.
- Suppress warning mà không kèm điều kiện an toàn rõ ràng.

## 18. Quy trình xử lý warning khi review mã

Khi gặp `unchecked` hoặc `rawtypes` trong build, nên làm theo trình tự:

1. **Bật chẩn đoán cụ thể:** `javac -Xlint:unchecked -Xlint:rawtypes`, hoặc cấu hình công cụ build tương ứng.
2. **Tìm đúng biểu thức:** nhận diện khai báo raw, lời gọi method, phép gán hay phép cast tạo warning.
3. **Xác định hợp đồng bị mất:** phần tử đáng lẽ là kiểu gì, ai có thể sửa collection, ai tạo dữ liệu?
4. **Ưu tiên sửa chữ ký:** thêm type parameter, wildcard hoặc type bounds phù hợp.
5. **Với dữ liệu từ bên ngoài:** kiểm tra kiểu phần tử tại biên và sao chép nếu cần ngăn alias.
6. **Với varargs:** đánh giá có ghi/tiết lộ mảng varargs hay không; chỉ dùng `@SafeVarargs` nếu method thực sự an toàn.
7. **Nếu bắt buộc suppress:** giải thích bằng chứng an toàn và giới hạn phạm vi annotation.
8. **Kiểm thử đường lỗi:** thử dữ liệu sai kiểu, null, collection bị mutate và các trường hợp biên.
9. **Đánh giá tương thích:** thay đổi API raw sang generic có thể tác động tới source compatibility và warning của client; cần kế hoạch migration khi thư viện có nhiều bên dùng.

### 18.1. Nên sửa warning ở nơi phát sinh, không phải nơi lỗi xuất hiện

Giả sử service A tạo `List<String>`, adapter B chuyển sang raw, service C đọc phần tử. `ClassCastException` có thể nổ ở service C, nhưng giải pháp bền vững thường nằm ở **adapter B** hoặc ở hợp đồng API tại ranh giới A–B–C.

Bắt `ClassCastException` ở mọi chỗ đọc rồi bỏ qua phần tử xấu có thể che giấu dữ liệu sai và khiến hệ thống khó chẩn đoán.

### 18.2. Không đánh đồng suppress warning với kỹ thuật migration

Khi buộc phải giữ tương thích với API raw chưa sửa được, hãy cô lập đoạn tiếp xúc trong một adapter nhỏ:

```text
External raw API
       |
       v
Adapter: đọc như List<?>, kiểm tra từng phần tử
       |
       v
List<String> mới có bất biến rõ ràng
       |
       v
Các service nội bộ dùng generics an toàn
```

Để raw type lan rộng trong toàn bộ ứng dụng đồng nghĩa với việc mất lợi ích chính của generics ở nhiều tầng.

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Raw `List` và `List<Object>` là một | Raw bỏ type argument; `List<Object>` vẫn là một parameterized type |
| `List<?>` giống raw `List` | `List<?>` vẫn kiểm tra kiểu, không cho tùy ý thêm phần tử |
| Có warning nghĩa là chắc chắn heap pollution | Warning chỉ báo thao tác chưa chứng minh an toàn; có thể không có dữ liệu sai |
| Không có warning nghĩa là chắc chắn không có heap pollution | Warning có thể bị ẩn, mã biên dịch riêng, hoặc alias mảng che rủi ro |
| Unchecked cast sẽ kiểm tra mọi phần tử | Runtime thường chỉ kiểm tra được raw type của collection |
| Heap pollution luôn ném exception ngay | Có thể chỉ lỗi khi đọc hoặc sử dụng dữ liệu như kiểu cụ thể |
| Mọi `ClassCastException` đều là heap pollution | Cast sai bình thường cũng có thể gây `ClassCastException` |
| `new List<String>[5]` hợp lệ | Generic array creation với component type non-reifiable bị cấm |
| `List<?>[]` cũng bị cấm | Unbounded wildcard type là reifiable; mảng loại này có thể hợp lệ |
| `@SafeVarargs` làm runtime tự kiểm tra kiểu | Annotation chỉ là cam kết của tác giả và tác động đến warning |
| `@SuppressWarnings("unchecked")` sửa lỗi kiểu | Nó chỉ ẩn cảnh báo |
| Có thể dùng `instanceof List<String>` | Type argument không reifiable; nên dùng `List<?>` và kiểm tra phần tử |
| Chỉ cần thêm `<>` khi `new ArrayList<>()` | Biến khai báo raw vẫn là raw dù constructor dùng diamond |
| `Collections.checkedList` bảo vệ mọi alias | View chỉ kiểm soát thao tác ghi đi qua chính view |
| Có thể lưu mutable collection raw rồi ép kiểu khi cần | Alias raw có thể phá ràng buộc kiểu bất kỳ lúc nào |

## 20. Bài tập thực hành

### Bài 1: Phân loại cảnh báo

Xét mã:

```java
List<String> words = new ArrayList<>();
List raw = words;
raw.add(10);
List<String> copy = raw;
```

Hãy xác định câu lệnh có thể tạo warning `rawtypes`, `unchecked call` và `unchecked conversion` khi bật các tùy chọn `-Xlint`. Chỉ ra thời điểm heap pollution xuất hiện và vị trí `ClassCastException` có thể xảy ra.

### Bài 2: Chuyển raw type thành wildcard

Viết lại method này sao cho không dùng raw type:

```java
static void showItems(List items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Sau đó thử truyền `List<String>`, `List<Integer>` và giải thích vì sao method mới vẫn sử dụng được với cả hai loại.

### Bài 3: Viết adapter kiểm tra kiểu

Giả sử một API trả về `List<?> values`. Viết method `toIntegers(List<?> values)` trả về `List<Integer>` mới, từ chối mọi phần tử không phải `Integer` và mọi phần tử `null`. Không dùng unchecked cast hoặc suppression.

### Bài 4: Tìm heap pollution trong varargs

Phân tích vì sao code sau nguy hiểm:

```java
static void dangerous(List<String>... parts) {
    Object[] array = parts;
    array[0] = List.of(99);
    System.out.println(parts[0].get(0).length());
}
```

Sửa method để chỉ đọc và sao chép dữ liệu. Đánh giá xem `@SafeVarargs` có hợp lý sau khi sửa hay không.

### Bài 5: Giải thích @SafeVarargs

Với mỗi khai báo dưới đây, hãy xác định có được phép dùng `@SafeVarargs` hay không và có đáng dùng không:

```java
static <T> void a(T... items) { }

final <T> void b(T... items) { }

private <T> void c(T... items) { }

public <T> void d(T... items) { }

static void e(String... items) { }
```

Lưu ý tính hợp lệ về **vị trí đặt annotation** khác với việc **thân method thực sự an toàn**.

### Bài 6: Thử xem lỗi xảy ra khi nào

Viết chương trình tạo một `List<String>`, sử dụng raw alias để thêm một `Integer`, sau đó:

1. In `list.size()`.
2. Duyệt danh sách qua `List<?>`, in từng phần tử dưới dạng `Object`.
3. Đọc phần tử `Integer` qua biến khai báo `List<String>` vào biến `String`.

Giải thích vì sao hai bước đầu có thể chạy thành công nhưng bước cuối lại thất bại.

### Bài 7: Review boundary adapter

Bạn nhận một collection có thể được thay đổi từ một thư viện bên ngoài. Hãy đề xuất cách tạo danh sách `List<String>` riêng và quyết định các quy tắc:

- Có cho phép `null` không?
- Nếu phần tử sai kiểu, trả về lỗi hay bỏ qua?
- Có cần thứ tự ban đầu không?
- Có cần copy dữ liệu ngay tại biên không?
- Có cần trả danh sách bất biến không?

Giải thích cách những quyết định này giúp bảo toàn hợp đồng kiểu và hạn chế việc heap pollution lan vào domain logic.

## 21. Tóm tắt

**Raw type** là cách sử dụng tên kiểu generic mà không kèm type argument. Java vẫn hỗ trợ nó để duy trì khả năng tương tác, nhưng raw reference làm mất nhiều bảo đảm của generic type checking.

**Unchecked warning** báo rằng compiler cho phép một thao tác mà không thể xác minh hoàn toàn kiểu tham số hóa. Các trường hợp thường gặp là unchecked call, conversion, cast và varargs với kiểu non-reifiable. `rawtypes` là nhóm cảnh báo riêng cho việc dùng raw type.

**Heap pollution** là tình trạng một tham chiếu có kiểu tham số hóa không phản ánh đúng kiểu dữ liệu thực tế mà nó trỏ đến. Hậu quả có thể chỉ lộ ra sau đó dưới dạng `ClassCastException`. Type erasure lý giải vì sao runtime không thể kiểm tra mọi type argument, còn generic varargs và alias mảng cho thấy nguy cơ ngay cả khi không có phép cast raw trực tiếp.

Khi xử lý Java generics hiện hành, hãy **ưu tiên kiểu tham số hóa, wildcard và kiểm tra dữ liệu ở ranh giới**. Với non-reifiable varargs, chỉ đặt `@SafeVarargs` khi thân method thực sự an toàn. Chỉ dùng `@SuppressWarnings("unchecked")` trong phạm vi nhỏ khi có bằng chứng rõ ràng. Một build ít cảnh báo chỉ có giá trị khi các hợp đồng kiểu cũng được bảo toàn.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 26 — §4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.6)
- [Java Language Specification, Java SE 26 — §4.7 Reifiable Types](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.7)
- [Java Language Specification, Java SE 26 — §4.8 Raw Types](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.8)
- [Java Language Specification, Java SE 26 — §4.12.2 Variables of Reference Type / Heap Pollution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.12.2)
- [Java Language Specification, Java SE 26 — §5.1.9 Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.1.9)
- [Java Language Specification, Java SE 26 — §9.6.4.7 @SafeVarargs](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.6.4.7)
- [Java SE 26 API — @SafeVarargs](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/SafeVarargs.html)
