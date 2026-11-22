# 8.6. Chọn nhánh bằng `MethodHandles.guardWithTest` và đồng nhất kiểu của hai nhánh

`java.lang.invoke.MethodHandles.guardWithTest(test, target, fallback)` là một **combinator** tạo ra `MethodHandle` có hành vi tương tự `if/else`: mỗi lần gọi handle kết quả, JVM gọi `test`, nếu nhận `true` thì chạy `target`, ngược lại chạy `fallback`. Điểm khó nhất không nằm ở phép `if`, mà ở **hợp đồng kiểu (`MethodType`)**: hai nhánh phải có kiểu **trùng khớp hoàn toàn**, còn hàm kiểm tra phải trả về `boolean` nguyên thủy và chỉ được đọc một **tiền tố** các tham số của hai nhánh.

Mục tiêu của bài:

- Hiểu chữ ký, dòng chảy thực thi và thời điểm kiểm tra kiểu của `guardWithTest`.
- Tạo được cả hai nhánh `target`/`fallback` có cùng một `MethodType`, kể cả khi method gốc có kiểu trả về hoặc số tham số khác nhau.
- Biết khi nào dùng `asType`, `dropArguments`, `constant`, `insertArguments` hay `permuteArguments` để **chủ động thích nghi** method handle trước khi ghép.
- Phân biệt lỗi **khi tạo combinator** (`IllegalArgumentException`) với lỗi **khi invoke** (`WrongMethodTypeException`, `ClassCastException` hoặc exception của nhánh được chọn).
- Sử dụng đúng `invokeExact`, tránh dựa vào chuyển kiểu ngầm và hiểu rằng `guardWithTest` không tự bắt lỗi của nhánh thất bại.

Bài dùng Java 17+; chương trình độc lập ở mục 4 đã được biên dịch với `javac --release 17` và chạy để kiểm tra chính xác stdout.

## 1. Tư duy như một biểu thức `if/else` có chữ ký rõ ràng

API:

```java
MethodHandle result = MethodHandles.guardWithTest(
        test, target, fallback);
```

Đây là một **đoạn mã minh họa**; `test`, `target`, `fallback` là các `MethodHandle` đã tồn tại và phải đáp ứng hợp đồng ở phần tiếp theo.

Ngữ nghĩa:

```text
                   invoke result(a..., b...)
                               |
                               v
                          test(a...)
                               |
                      +--------+--------+
                      |                 |
                    true              false
                      |                 |
                      v                 v
              target(a..., b...)  fallback(a..., b...)
                      |                 |
                      +--------+--------+
                               |
                       trả về cùng kiểu T
```

Giả sử `target` và `fallback` đều nhận các đối số `(A..., B...)` và cùng trả về `T`, trong khi `test` chỉ nhận tiền tố `(A...)` và trả về `boolean`:

```text
test     : (A...)boolean
target   : (A..., B...)T
fallback : (A..., B...)T
result   : (A..., B...)T
```

Chẳng hạn:

```text
test     : (int)boolean
target   : (int, String)String
fallback : (int, String)String
result   : (int, String)String
```

Ở mỗi lần gọi `result`:

1. `test` nhận đối số `int` đầu tiên và trả `true` hoặc `false`.
2. `true` chọn `target`, `false` chọn `fallback`.
3. Nhánh được chọn nhận **đầy đủ** các đối số gốc theo đúng thứ tự.
4. Nhánh không được chọn **không bị gọi**.
5. `result` có cùng kiểu với `target` và `fallback`, không phải kiểu của `test`.

Adapter được tạo **một lần** khi gọi `guardWithTest`; biểu thức kiểm tra được chạy **mỗi khi** invoke adapter, trừ khi ứng dụng cố định/biến đổi adapter bằng các kỹ thuật riêng. Không có chuyện tạo lại hai method handle thành viên ở mỗi lời gọi chỉ vì `test` được tính lại.

## 2. Hợp đồng kiểu bắt buộc

### 2.1. Hai nhánh phải giống nhau tuyệt đối

Điều kiện trung tâm:

```java
target.type().equals(fallback.type())
```

Đây là **đoạn minh họa rời**, dùng hai biến handle đã có. `MethodType.equals` so sánh chính xác kiểu trả về, số tham số, thứ tự tham số và từng `Class<?>` của các tham số.

Ví dụ:

| `target.type()` | `fallback.type()` | Ghép trực tiếp được không? | Lý do |
| --- | --- | --- | --- |
| `(int)String` | `(int)String` | Có | Trùng khớp hoàn toàn |
| `(int, String)String` | `(int, String)String` | Có | Trùng toàn bộ kiểu và thứ tự |
| `(int)String` | `(long)String` | Không | `int` khác `long`, dù Java có widening khi gọi method thông thường |
| `(int)String` | `(Integer)String` | Không | `int` khác `Integer`, dù có boxing/unboxing ở ngữ cảnh khác |
| `(int)String` | `(int)Object` | Không | `String` khác `Object`, dù `String` là subtype của `Object` |
| `(int, String)void` | `(int, String)String` | Không | `void` khác `String` |
| `(int, String)String` | `(String, int)String` | Không | Thứ tự tham số khác nhau |

`guardWithTest` **không tự gọi `asType`** để làm hai nhánh tương thích. Nếu kiểu gốc khác nhau, lập trình viên phải chọn **một chữ ký đích chung**, rồi chuyển đổi từng nhánh một cách có kiểm soát trước khi ghép.

Một nhánh trả về `void` hoàn toàn hợp lệ **nếu cả hai nhánh cùng trả về `void`**. Khi đó handle kết quả cũng trả `void`.

### 2.2. `test` phải trả `boolean` nguyên thủy

Hàm kiểm tra bắt buộc có kiểu trả về **`boolean.class`**, không phải `Boolean.class`, `int.class` hay `Object.class`.

Ví dụ:

```text
(int)boolean    -> hợp lệ nếu các tham số là tiền tố
(int)Boolean    -> không hợp lệ khi ghép trực tiếp
()boolean       -> hợp lệ; test không sử dụng tham số nào
```

Nếu predicate gốc trả `Boolean`, có thể cân nhắc thích nghi bằng `asType` sang `boolean`; cần hiểu thao tác unboxing có thể ném `NullPointerException` nếu predicate trả `null`. Trong đa số trường hợp, thiết kế predicate trả primitive `boolean` rõ ràng hơn.

### 2.3. Tham số của `test` phải là **tiền tố liên tục**

Với nhánh có kiểu:

```text
(int, String, long)String
```

Những kiểu `test` hợp lệ về số lượng/thứ tự tham số là:

```text
()boolean
(int)boolean
(int, String)boolean
(int, String, long)boolean
```

Còn các kiểu sau không hợp lệ để ghép **trực tiếp**:

```text
(String)boolean             // lấy tham số thứ hai, không phải tiền tố
(int, long)boolean          // bỏ qua String ở giữa
(int, String, long, int)boolean // quá nhiều tham số
(int)Boolean                // kiểu trả về không phải primitive boolean
(long)boolean               // tham số đầu không trùng int
```

Nếu predicate cần tham số ở vị trí khác, có thể tạo handle mới có chữ ký **đúng vị trí** bằng `dropArguments`, `permuteArguments`, `filterArguments` hoặc các combinator thích hợp. Không được giả định `guardWithTest` tự tìm tham số tương ứng theo tên hoặc tự sắp xếp lại thứ tự.

### 2.4. Kết quả không tự thay đổi type giữa các lần gọi

Do hai nhánh cùng một `MethodType`, adapter cũng có đúng `MethodType` ấy:

```java
MethodHandle result = MethodHandles.guardWithTest(
        test, target, fallback);
System.out.println(result.type().equals(target.type())); // true
```

Đây là **đoạn minh họa rời** sử dụng các handles đã được tạo hợp lệ. Dù tại runtime có lần đi nhánh `target`, có lần đi `fallback`, chữ ký của `result` vẫn không đổi. Vì thế caller có thể dùng một `invokeExact` với type rõ ràng mà không cần biết kết quả test.

## 3. Thời điểm kiểm tra và thứ tự thực thi

Có hai tầng cần tách:

**Tầng A — khi ghép adapter:**

- `guardWithTest` nhận ba handles, kiểm tra `null`, kiểu trả về của predicate, kiểu hai nhánh và quy tắc tiền tố.
- Nếu không hợp lệ, API ném `NullPointerException` hoặc **`IllegalArgumentException`** ngay lúc *xây dựng* adapter.
- Nó **không tự chạy `test`, `target`, `fallback`** để thử kết quả khi ghép.
- Nếu một handle thành viên trước đó được tạo bằng `Lookup.findStatic`/`findVirtual`, các access checks của factory đó là một vấn đề riêng: chúng đã xảy ra khi tìm method.

**Tầng B — khi gọi adapter:**

- JVM gọi `test` với tiền tố tham số từ lời gọi.
- Nếu `test` trả `true` thì chỉ chạy `target`; `false` thì chỉ chạy `fallback`.
- Không có tự động chuyển sang `fallback` khi `test` ném exception; exception được lan truyền. Nếu `target` được chọn rồi ném exception, `fallback` **không** được gọi như một catch handler.
- Caller vẫn phải gọi handle bằng đúng `MethodType`, đặc biệt với `invokeExact`.
- Mỗi nhánh nhận các đối số gốc, không phải giá trị `boolean` mà `test` trả về.

Cần phân biệt **truyền nguyên đối số** và **bất biến trạng thái**: combinator không thay thế hoặc loại bỏ các đối số trước khi chuyển cho nhánh; tuy vậy một predicate có side effect vẫn có thể thay đổi **trạng thái của object** được truyền bằng reference hoặc dữ liệu dùng chung. Vì thế predicate nên được viết ngắn, dễ dự đoán và lý tưởng là không có tác dụng phụ.

## 4. Chương trình Java 17+ chạy độc lập: chọn nhánh và xử lý mismatch

Lưu toàn bộ mã bên dưới vào **`GuardWithTestDemo.java`**. Class `GuardWithTestDemo` dùng static methods để không cần xử lý receiver; chúng ta tập trung vào `MethodType` và compositional logic.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class GuardWithTestDemo {
    static boolean nonNegative(int value) {
        System.out.println("test(" + value + ")");
        return value >= 0;
    }

    static String accepted(int value, String tag) {
        System.out.println("target");
        return "ok[" + tag + "]=" + value;
    }

    static String rejected(int value, String tag) {
        System.out.println("fallback");
        return "no[" + tag + "]=" + value;
    }

    static Object rejectedObject(int value, String tag) {
        return "objectFallback[" + tag + "]=" + value;
    }

    static boolean vip(String tag) {
        return "vip".equals(tag);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Predicate chỉ nhận tiền tố int.
        MethodHandle test = lookup.findStatic(
                GuardWithTestDemo.class, "nonNegative",
                MethodType.methodType(boolean.class, int.class));

        // Hai nhánh phải có cùng MethodType.
        MethodType commonType = MethodType.methodType(
                String.class, int.class, String.class);
        MethodHandle target = lookup.findStatic(
                GuardWithTestDemo.class, "accepted", commonType);
        MethodHandle fallback = lookup.findStatic(
                GuardWithTestDemo.class, "rejected", commonType);

        MethodHandle route = MethodHandles.guardWithTest(test, target, fallback);
        System.out.println("testType=" + test.type());
        System.out.println("routeType=" + route.type());
        System.out.println("first=" + (String) route.invokeExact(7, "A"));
        System.out.println("second=" + (String) route.invokeExact(-3, "B"));

        // Nhánh fallback gốc ()String: mở rộng để nhận (int,String).
        MethodHandle constantFallback = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "blocked"),
                0, int.class, String.class);
        MethodHandle blocked = MethodHandles.guardWithTest(
                test, target, constantFallback);
        System.out.println("blocked=" + (String) blocked.invokeExact(-1, "C"));

        // Sai vì một nhánh trả Object, nhánh còn lại trả String.
        MethodHandle objectFallback = lookup.findStatic(
                GuardWithTestDemo.class, "rejectedObject",
                MethodType.methodType(Object.class, int.class, String.class));
        try {
            MethodHandles.guardWithTest(test, target, objectFallback);
            System.out.println("mismatch=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("mismatch=rejected");
        }

        // Chuyển Object -> String bằng runtime cast rõ ràng.
        MethodHandle convertedFallback = objectFallback.asType(commonType);
        MethodHandle converted = MethodHandles.guardWithTest(
                test, target, convertedFallback);
        System.out.println("adapted=" + (String) converted.invokeExact(-2, "D"));

        // Predicate (String)boolean không phải tiền tố của (int,String).
        MethodHandle byTag = lookup.findStatic(
                GuardWithTestDemo.class, "vip",
                MethodType.methodType(boolean.class, String.class));
        try {
            MethodHandles.guardWithTest(byTag, target, fallback);
            System.out.println("nonprefix=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nonprefix=rejected");
        }

        // Chèn int không sử dụng ở đầu: (int,String)boolean.
        MethodHandle tagTest = MethodHandles.dropArguments(
                byTag, 0, int.class);
        MethodHandle tagRoute = MethodHandles.guardWithTest(
                tagTest, target, fallback);
        System.out.println("vip=" + (String) tagRoute.invokeExact(5, "vip"));
        System.out.println("normal=" + (String) tagRoute.invokeExact(5, "user"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 GuardWithTestDemo.java
java GuardWithTestDemo
```

**Stdout chính xác** của chương trình:

```text
testType=(int)boolean
routeType=(int,String)String
test(7)
target
first=ok[A]=7
test(-3)
fallback
second=no[B]=-3
test(-1)
blocked=blocked
mismatch=rejected
test(-2)
adapted=objectFallback[D]=-2
nonprefix=rejected
target
vip=ok[vip]=5
fallback
normal=no[user]=5
```

Lưu ý cách `MethodType.toString()` hiển thị `(int,String)String` không có khoảng trắng sau dấu phẩy. Đó là biểu diễn tiêu chuẩn của Java, không phải một chuỗi tự đặt tùy ý.

### 4.1. Đọc trace của lần gọi thứ nhất và thứ hai

Dòng `test(7)` xuất hiện trước `target` bởi `test` được chạy đầu tiên, trả `true`. Kết quả `first=ok[A]=7` đến từ `accepted`.

Ở lượt gọi `(-3, "B")`, `test(-3)` trả `false`; chỉ `fallback` in ra và `rejected` tạo `second=no[B]=-3`.

Tham số `"A"` hoặc `"B"` không được truyền cho `nonNegative` vì test chỉ cần `int`. Nhưng cả hai tham số đều được chuyển nguyên vị trí vào nhánh được chọn.

### 4.2. Vì sao `blocked=blocked` không in `fallback`?

`constantFallback` được tạo từ:

```java
MethodHandles.constant(String.class, "blocked")
```

Nó có kiểu `()String`: trả về hằng số mà không nhận đối số. Sau đó:

```java
MethodHandles.dropArguments(
        constant, 0, int.class, String.class)
```

(hai đoạn trên dùng biến `constant` minh họa từ kết quả của `constant(...)`) tạo handle mới kiểu `(int,String)String`, **bỏ qua** hai đối số mà adapter nhận. Khi test trả `false`, nhánh mới trả `"blocked"` ngay, không gọi `rejected`, vì nhánh fallback bây giờ là constant adapter.

Quan trọng: `dropArguments` không thay đổi method handle gốc và không tự gán giá trị mặc định cho những đối số caller thiếu. Nó làm cho handle mới **nhận thêm** đối số rồi bỏ qua chúng khi ủy quyền.

### 4.3. Vì sao nhánh `Object` bị từ chối dù giá trị thực là `String`?

`rejectedObject` có chữ ký `(int,String)Object`, mặc dù thực tế trả về một object là `String`. Còn `accepted` có kiểu `(int,String)String`.

`guardWithTest` so sánh **khai báo `MethodType`**, không chạy nhánh để xem object thực sự thuộc class nào. Vì vậy lần ghép đầu ném `IllegalArgumentException`.

Cách sửa ở ví dụ:

```java
MethodHandle convertedFallback = objectFallback.asType(commonType);
```

Dòng này yêu cầu method handle mới có kiểu `(int,String)String`. Đến khi thực thi nhánh, adapter thực hiện chuyển kiểu kết quả từ `Object` về `String` (với điều kiện giá trị runtime thật sự phù hợp).

Nếu `rejectedObject` trả một object không ép được thành `String`, lời gọi trên handle đã được ghép có thể thất bại với **`ClassCastException` lúc chạy**. `asType` giải quyết **chữ ký adapter**, không chứng minh mọi dữ liệu runtime đều hợp lệ.

### 4.4. Vì sao `(String)boolean` chưa phù hợp và `dropArguments` lại giúp được?

`byTag` có kiểu `(String)boolean`, nhưng `target` và `fallback` nhận `(int,String)`. `test` chỉ được lấy **tiền tố**, mà tiền tố một phần tử của `(int,String)` là `(int)`, không phải `(String)`.

`dropArguments(byTag, 0, int.class)` tạo test mới `(int,String)boolean`: nó nhận `int` đầu tiên và **bỏ qua** nó, sau đó chuyển `String` thứ hai tới predicate `vip`.

Hai lời gọi cuối chứng minh `tagRoute` chọn target cho tag `"vip"`, fallback cho tag `"user"`, mặc dù `value` giống nhau.

## 5. Bốn kỹ thuật đồng nhất kiểu trước khi ghép

Khi các handles chưa có cùng chữ ký, làm theo thứ tự: **chọn `MethodType` chung → xem loại khác biệt → adapt từng handle → kiểm tra `type()` → ghép**.

### 5.1. `asType` — thích nghi kiểu tham số hoặc kiểu trả về khi hợp lệ

Ví dụ đã kiểm chứng:

```java
MethodType commonType = MethodType.methodType(
        String.class, int.class, String.class);
MethodHandle adjustedFallback = objectFallback.asType(commonType);
```

Đây là **đoạn mã minh họa trong ngữ cảnh chương trình mục 4**. Trước khi adapt:

```text
objectFallback : (int,String)Object
target         : (int,String)String
```

Sau khi adapt:

```text
adjustedFallback : (int,String)String
target           : (int,String)String
```

`asType` có thể chèn những chuyển đổi được Java `MethodHandle` hỗ trợ, chẳng hạn reference cast, boxing/unboxing hoặc primitive conversions tương ứng. Nó **không** bảo đảm mọi chuyển đổi đều an toàn: một số lỗi có thể xảy ra khi tạo adapter (`WrongMethodTypeException` với conversion không hỗ trợ) hoặc khi invoke (ví dụ cast sai kiểu, unboxing `null`).

**Không dùng `asType` để che giấu mô hình dữ liệu không rõ ràng.** Nếu hai nhánh tự nhiên trả hai loại kết quả khác nhau, hãy quyết định một contract chung hợp lý, như một interface/record kết quả thống nhất, thay vì cưỡng ép cast tùy tiện.

### 5.2. `dropArguments` — bổ sung tham số bị bỏ qua

Trường hợp fallback không cần mọi đối số:

```text
constant(String.class, "blocked") : ()String
target                            : (int,String)String
```

Sau:

```java
MethodHandle fallbackFull = MethodHandles.dropArguments(
        MethodHandles.constant(String.class, "blocked"),
        0, int.class, String.class);
```

ta có `fallbackFull.type() == (int,String)String`. Đây là cú pháp **độc lập về mặt biểu thức** nếu có `import java.lang.invoke.MethodHandle;` và `import java.lang.invoke.MethodHandles;`, nhưng chỉ là đoạn minh họa chứ không phải chương trình hoàn chỉnh.

Bạn có thể đặt những đối số bổ sung ở `pos` phù hợp, miễn thứ tự kết quả cuối cùng khớp chữ ký chung.

**Lưu ý tinh tế:** `dropArguments` *thêm* parameters vào chữ ký handle mới nhưng *không* dùng chúng. Đừng nhầm với việc loại bỏ tham số thật khỏi call site. Nếu cần cố định một giá trị cho handle gốc, xem `insertArguments`.

### 5.3. `insertArguments` — gắn trước giá trị cho một số tham số

Giả sử một method gốc là:

```java
static String prefix(String label, int number) {
    return label + number;
}
```

Đây là **khai báo minh họa**. Khi `findStatic` đã trả handle kiểu `(String,int)String`, có thể gắn nhãn `"OK:"`:

```java
MethodHandle adjusted = MethodHandles.insertArguments(
        original, 0, "OK:");
```

`adjusted` sẽ có kiểu `(int)String`, vì tham số đầu `String` đã được cung cấp trước. Để ghép vào một guard có cả hai nhánh `(int)String`, cần cho nhánh còn lại cũng có kiểu `(int)String` hoặc thích nghi nó tương ứng.

`insertArguments` không làm predicate tự đổi chữ ký. Trước khi gọi `guardWithTest`, hãy so sánh **cả ba** handle sau khi adapt; không chỉ so hai nhánh.

### 5.4. `permuteArguments` — sắp xếp lại đối số khi predicate hoặc nhánh cần thứ tự khác

Một predicate có thể cần đối số nằm ở giữa/cuối hoặc một nhánh gốc có thứ tự parameters khác. `permuteArguments` cho phép tạo handle với thứ tự input mới rồi ánh xạ chúng tới arguments của handle cũ.

Ví dụ, với handle gốc `h` có kiểu `(String,int)String`, ta muốn handle nhận `(int,String)String` nhưng đưa chúng tới `h` ở thứ tự ngược lại:

```java
MethodType newType = MethodType.methodType(
        String.class, int.class, String.class);
MethodHandle reordered = MethodHandles.permuteArguments(
        h, newType, 1, 0);
```

**Đoạn minh họa** giả định biến `h` đúng kiểu `(String,int)String` đã tồn tại. `reordered` có kiểu `(int,String)String`: `h` nhận `(String)` từ đối số mới chỉ số `1`, và `(int)` từ đối số mới chỉ số `0`. Cần hiểu chỉ số ánh xạ là **zero-based**.

Không dùng `permuteArguments` để tự chuyển `String` thành `int`. Nó điều chỉnh **mapping và thứ tự**, không phải parser dữ liệu. Nếu hai nhánh sau hoán vị vẫn không có chính xác cùng kiểu, phải tiếp tục xử lý.

## 6. Kiểm tra `MethodType` trước khi ghép

Trong framework hoặc adapter tạo động, log chữ ký thường tiết kiệm rất nhiều thời gian:

```java
System.out.println("test=" + test.type());
System.out.println("target=" + target.type());
System.out.println("fallback=" + fallback.type());
```

Đây là **đoạn minh họa rời** với các biến handle đã được tạo.

Nếu tự validate trước, có thể áp dụng trình tự:

1. `test != null && target != null && fallback != null`.
2. `target.type().equals(fallback.type())`.
3. `test.type().returnType() == boolean.class`.
4. `test.type().parameterCount() <= target.type().parameterCount()`.
5. Danh sách tham số của test bằng **prefix cùng độ dài** của `target.type().parameterList()`.

Một cách kiểm tra tối thiểu trong Java khi các handles đã tồn tại:

```java
MethodType targetType = target.type();
MethodType fallbackType = fallback.type();
MethodType predicateType = test.type();

if (!targetType.equals(fallbackType)) {
    throw new IllegalArgumentException("Branches have different MethodTypes");
}
if (predicateType.returnType() != boolean.class) {
    throw new IllegalArgumentException("Test must return primitive boolean");
}
int count = predicateType.parameterCount();
if (count > targetType.parameterCount()
        || !predicateType.parameterList().equals(
                targetType.parameterList().subList(0, count))) {
    throw new IllegalArgumentException("Test parameters must be a prefix");
}
```

Đây là **đoạn minh họa dùng biến `test`, `target`, `fallback` đã có** và cần import `MethodType`; không phải một file Java độc lập. `guardWithTest` vẫn tự kiểm tra điều kiện; validation trên chỉ giúp tạo thông báo có ngữ cảnh hơn ở tầng ứng dụng.

Trong thiết kế thực tế, nên chuẩn hóa `MethodType` trước khi tạo adapter thay vì xây rồi dựa vào exception để suy đoán. Tuy nhiên, đừng bao lấy mọi `RuntimeException` rồi gắn nhãn “lỗi kiểu” vì một `RuntimeException` xuất hiện **khi invoke nhánh** có thể là lỗi nghiệp vụ hoàn toàn khác.

## 7. `invokeExact` và `invoke`: đừng để lỗi call site che lỗi ghép

Ví dụ adapter có chữ ký:

```text
(int,String)String
```

Một lời gọi chính xác là:

```java
String result = (String) route.invokeExact(7, "A");
```

Đây là **đoạn trong chương trình ở mục 4**, `route` là handle `(int,String)String`.

Với `invokeExact`, call site phải thể hiện đúng:

- Tham số thứ nhất `int`, không phải `long` hay `Integer`.
- Tham số thứ hai `String`, không phải một `Object` chỉ tình cờ đang chứa `String`.
- Giá trị trả về theo chữ ký là `String`, không phải `Object` hoặc một ngữ cảnh `void`.

Vì là signature-polymorphic invocation, biểu thức ép kiểu kết quả và ngữ cảnh static type của call site ảnh hưởng đến chữ ký mà JVM kỳ vọng. Code trông tương tự Java thông thường vẫn có thể ném `WrongMethodTypeException` khi chữ ký không đúng.

`invoke` cho phép adaptation theo các quy tắc chuyển kiểu của MethodHandle, nhưng không nên dựa vào nó để thay cho việc thiết kế contract. Với thư viện/DSL cần ổn định chữ ký, `invokeExact` thường giúp phát hiện lỗi sớm và rõ hơn.

**Quan trọng:** `guardWithTest` đã tạo thành công **không đồng nghĩa** mọi `invokeExact` đều sẽ chạy. Đây là hai lớp kiểm tra khác nhau: composition type versus invocation call-site type.

## 8. Khi `test` hoặc nhánh ném exception

`guardWithTest` là combinator **chọn nhánh**, không phải bộ xử lý exception.

Giả sử test là:

```java
static boolean eligible(int value) {
    if (value == 0) {
        throw new IllegalStateException("Unknown");
    }
    return value > 0;
}
```

Đây là **khai báo ví dụ**, chưa phải một class chạy độc lập.

Khi `eligible(0)` ném exception, cả `target` và `fallback` **không** được gọi. Adapter truyền exception đó ra caller.

Tương tự, nếu `test` trả `true`, `target` được gọi và `target` ném exception, thì `fallback` **không** phải “nhánh dự phòng” để bắt lỗi. Nó chỉ chạy khi **predicate trả `false`**.

Nếu mục tiêu là xử lý exception của target, hãy cân nhắc một combinator khác như `MethodHandles.catchException(...)`, với chữ ký handler riêng, hoặc dùng try/catch phù hợp ở tầng bao ngoài. Nếu mục tiêu là nhánh thực thi theo state và cần hủy khả năng sau một sự kiện, `SwitchPoint.guardWithTest` là một API khác với đặc tính invalidation, không đồng nghĩa với `MethodHandles.guardWithTest`.

Một bẫy dễ bỏ qua: vì test được gọi mỗi lần, một test phụ thuộc thời gian, thread-local state, cache hoặc global flag có thể chọn nhánh khác ở các lần gọi liên tiếp. `guardWithTest` không tự khóa hay làm bộ nhớ chia sẻ trở nên thread-safe. Thiết kế guard có side effect hoặc race condition có thể tạo lỗi logic khó tái hiện.

## 9. Đồng nhất kiểu khi hai nhánh đến từ API khác nhau

Một tình huống điển hình: thư viện A trả `int`, thư viện B trả `long`, hoặc một nhánh trả `String`, nhánh khác trả `Object`. Cách chọn chữ ký chung ảnh hưởng trực tiếp đến semantics:

| Vấn đề | Phương án đúng hướng | Điều cần cân nhắc |
| --- | --- | --- |
| Khác kiểu primitive như `int`/`long` | Chọn `long` chung nếu nghiệp vụ cho phép và adapt có kiểm soát | Widening có thể phù hợp; narrowing có thể mất dữ liệu |
| `String` so với `Object` | Chọn `Object` chung hoặc cast `Object` về `String` khi có bảo đảm | Chọn `String` chỉ khi object thật sự luôn là `String` |
| Nhánh không cần một số tham số | `dropArguments` để thêm các tham số bị bỏ qua | Những tham số ấy không được dùng/validate trong nhánh đó |
| Nhánh trả một hằng số | `constant` rồi `dropArguments` | Hằng số có thể che giấu dữ liệu bị bỏ qua hoặc thiếu logging |
| Nhánh cần đối số thứ tự khác | `permuteArguments` hoặc adapter phù hợp | Kiểm tra chỉ số zero-based và chữ ký sau biến đổi |
| Nhánh yêu cầu giá trị cấu hình cố định | `insertArguments` | Giá trị bound có vòng đời và quyền truy cập riêng |
| Nhánh trả `void`, nhánh trả giá trị | Chọn một contract thực sự hợp lý, adapt nếu API cho phép và có ý nghĩa | Đừng vô tình bỏ kết quả có giá trị nghiệp vụ |
| Predicate cần tham số ở giữa | Tạo predicate handle mới có full signature, ví dụ `dropArguments` tại vị trí thích hợp | Test chỉ được nhận tiền tố sau khi đã adapt |

Ví dụ `asType` từ `(int,String)Object` sang `(int,String)String` trong mục 4 có ý nghĩa vì nhánh đó **thực sự trả một `String`**. Nếu nhánh có thể trả `Integer` hoặc record khác, chuyển kiểu ấy không còn an toàn; chọn `Object`/interface kết quả hoặc tạo một mapper rõ ràng hơn.

Không có quy tắc “chọn kiểu rộng nhất bất kể dữ liệu”. Hãy chọn kiểu chung dựa trên contract, không chỉ để `guardWithTest` hết ném `IllegalArgumentException`.

### 9.1. Trường hợp nhận `void`

Nếu hai nhánh đều có kiểu `(String)void`, predicate có thể có kiểu `(String)boolean` hoặc `()boolean`. Adapter kết quả có kiểu `(String)void`; khi gọi `invokeExact`, dùng ngữ cảnh **không lấy kết quả**.

Không thể ghép trực tiếp nhánh `(String)void` với nhánh `(String)String`. Nếu kết quả `String` không quan trọng và chính sách cho phép, có thể chủ động adapt để bỏ kết quả; nếu không, thiết kế lại contract để hai nhánh cùng trả về dữ liệu hoặc cùng `void`. Không để mismatch bị giấu bởi việc một nhánh chỉ in log.

### 9.2. Trường hợp receiver instance method

`findVirtual` tạo handle có **receiver** nằm trong danh sách parameters của `MethodType`, thường là tham số đầu. Điều đó có nghĩa **predicate tiền tố có thể nhìn receiver trước**, thay vì nhìn tham số nghiệp vụ đầu của method gốc.

Ví dụ, với một handle có kiểu `(Service,int)String`, test có kiểu `(int)boolean` **không** là tiền tố; phải biến nó thành `(Service,int)boolean` hoặc một prefix phù hợp. Dùng `dropArguments` để thêm receiver bị bỏ qua vào test là một lựa chọn khi types chính xác. Tránh nhầm chữ ký Java của method `String serve(int)` với chữ ký handle instance `(Service,int)String`.

### 9.3. Trường hợp method access

Ba handle đưa vào `guardWithTest` phải **đã tồn tại**. Nếu tạo bằng `MethodHandles.Lookup`, việc `findStatic`/`findVirtual` có thành công hay không còn tùy quyền truy cập và module visibility.

Một lỗi `IllegalAccessException` khi **tìm** method handle không phải lỗi `guardWithTest` thiếu đồng nhất kiểu. Với ví dụ bài này, mọi method cần tìm đều nằm trong chính `GuardWithTestDemo`, vì vậy có thể dùng `MethodHandles.lookup()` và `findStatic` mà không cần thay đổi JPMS openness.

## 10. So sánh `guardWithTest` với `if/else` thông thường

| Tiêu chí | `if/else` Java | `MethodHandles.guardWithTest` |
| --- | --- | --- |
| Quy tắc kiểu | Compiler kiểm tra biểu thức/statement; các nhánh có thể có kiểu khác nhau tùy ngữ cảnh | Hai handles **bắt buộc cùng `MethodType`** khi ghép |
| Predicate | Biểu thức trả `boolean` Java | `MethodHandle` trả primitive `boolean` |
| Inputs của predicate | Có thể dùng các biến nhìn thấy trong scope | Nhận một prefix chính xác của inputs adapter (trừ khi đã adapt) |
| Xác định nhánh | Mỗi lần thực thi statement/expression | Mỗi lần invoke adapter (test chạy rồi chọn nhánh) |
| Vị trí xây dựng | Logic có trong mã nguồn/bytecode | Adapter được ghép động từ các handles hiện có |
| Lỗi kiểu | Thường xuất hiện lúc compile | `IllegalArgumentException` lúc ghép, hoặc lỗi call-site/adaptation lúc invoke |
| Trường hợp phù hợp | Logic nghiệp vụ thông thường | Framework runtime, dynamic dispatch, DSL, interpreter, tổ hợp handles |
| Độ dễ đọc | Thường rõ ràng hơn | Yêu cầu người đọc nắm `MethodType` và các combinators |

Với business logic bình thường, một `if/else` hoặc phương thức đa hình đơn giản có thể rõ ràng và dễ bảo trì hơn. `guardWithTest` hữu ích khi ứng dụng **đã làm việc với các MethodHandle như những khối gọi có thể kết hợp**, cần xây luồng gọi động mà không viết lại một class cho từng cấu hình.

## 11. Checklist chẩn đoán khi `guardWithTest` thất bại

Khi nhận `IllegalArgumentException` lúc ghép:

1. In `test.type()`, `target.type()`, `fallback.type()`.
2. So sánh **`target.type().equals(fallback.type())`**. Nếu không đúng, kiểm tra parameter count, thứ tự và return type.
3. Kiểm tra `test.type().returnType() == boolean.class`. `Boolean.class` không phải primitive `boolean`.
4. Đối chiếu danh sách parameters của test với **prefix cùng độ dài** của `target.type().parameterList()`. Một predicate lấy tham số ở giữa không hợp lệ trực tiếp.
5. Adapt từng handle riêng bằng `asType`, `dropArguments`, `insertArguments`, `permuteArguments` hoặc công cụ thích hợp; xác minh type **sau** mỗi bước.
6. Ghép lại và xác nhận `result.type().equals(target.type())`.

Khi lỗi chỉ xuất hiện **khi gọi**:

- `WrongMethodTypeException`: kiểm tra chữ ký `invokeExact`/`invoke` và adapter conversion.
- `ClassCastException`: một nhánh có thể trả object không khớp kiểu đã chọn bằng `asType`.
- `NullPointerException`: có thể do code trong predicate/branch hoặc do unboxing `null` trong adapter.
- `IllegalStateException` hay exception khác: có thể đến từ chính predicate/nhánh; `fallback` không tự bắt lỗi đó.
- Kết quả sai dù không lỗi: kiểm tra điều kiện test, thứ tự parameters và khả năng nhầm `target`/`fallback` khi ghép.
- Trace cho thấy cả nhánh “như được gọi”: xem lại code bên ngoài adapter hoặc side effect trong predicate; bản thân `guardWithTest` chỉ gọi **một nhánh** theo kết quả test.

**Mẹo kiểm thử:** viết một predicate in trace hoặc tăng bộ đếm test, hai nhánh in dấu riêng, rồi gọi adapter lần lượt bằng input `true` và `false`. Tránh đưa logging quá chi tiết vào code production có đường gọi nóng.

## 12. Tình huống áp dụng và giới hạn

**Routing theo loại yêu cầu:** predicate phân loại request rồi chọn fast path/fallback path; hai nhánh dùng chung interface kết quả. Khi hai nhánh có signatures gốc khác nhau, biến đổi về contract chung ở chỗ tạo adapter.

**Feature flag:** predicate đọc flag mỗi lần để chọn implementation. Cần chú ý consistency và visibility nếu flag có thể đổi đồng thời; `guardWithTest` không tự tạo đồng bộ hóa.

**Validation trước xử lý:** một predicate kiểm tra đầu vào, `target` xử lý hợp lệ, `fallback` tạo kết quả từ chối. Cả hai nhánh cần cùng `MethodType`, ví dụ `(Request)Result`. Nếu fallback chỉ cần hằng số lỗi, dùng `constant` + `dropArguments` hoặc adapter rõ ràng.

**Interpreter/DSL:** công cụ có thể tạo handles của điều kiện và hai nhánh từ metadata runtime. Đây là một trường hợp mà việc kiểm tra `MethodType` trước khi ghép có giá trị lớn; nên giữ một giai đoạn chuẩn hóa signatures.

**Giới hạn:** guard không phải catch handler; không tự convert mọi kiểu; không đảm bảo predicate side-effect-free; không phải boundary bảo mật độc lập; không tự đảm bảo tốt hơn `if/else` về hiệu năng. JVM có thể tối ưu một handle graph khi phù hợp, nhưng không nên tuyên bố một mức tăng tốc cố định nếu chưa benchmark trong ứng dụng thực tế.

## 13. Bài tập tự kiểm tra (kèm đáp án)

1. `target=(int,String)String`, `fallback=(int,String)String`, `test=(int)boolean`. Có ghép được không? **Có.** Test nhận tiền tố một tham số.
2. Vẫn hai nhánh trên nhưng `test=(String)boolean`. Có ghép trực tiếp được không? **Không.** `String` không phải tham số đầu; có thể thêm `int` bị bỏ qua phía trước bằng `dropArguments`.
3. `target=(int)String`, `fallback=(int)Object`. Có tự ghép vì `String extends Object` không? **Không.** `MethodType` của hai nhánh phải giống nhau tuyệt đối.
4. `target=(int)String`, `fallback=(int)String`, `test=(int)Boolean`. Có ghép trực tiếp được không? **Không.** Test phải trả primitive `boolean`.
5. `test=()boolean` còn hai nhánh `(int,String)String`. Có hợp lệ không? **Có.** Tiền tố rỗng được chấp nhận.
6. Nếu predicate trả `true` nhưng `target` ném exception, combinator sẽ tự gọi `fallback` không? **Không.** Exception của target được lan ra caller.
7. Nếu cần fallback luôn trả `"blocked"` mà không dùng hai tham số của target, dùng gì? **`constant(String.class, "blocked")` rồi `dropArguments` để tạo chữ ký trùng.**
8. Nếu adapt nhánh `(int)Object` về `(int)String` bằng `asType`, khi nhánh trả `Integer` thì sao? **Có thể ném `ClassCastException` lúc invoke.**
9. `invokeExact` trên adapter `(int,String)String` có thể sử dụng argument thứ nhất là `long` không? **Không**, call site phải trùng kiểu, nếu không có thể nhận `WrongMethodTypeException`.
10. Có thể dùng `guardWithTest` với hai nhánh trả `void` không? **Có**, miễn hai nhánh cùng kiểu và test thỏa điều kiện.
11. Predicate có được nhận tham số thứ ba mà bỏ hai tham số trước không? **Không trực tiếp**; cần tạo predicate handle mới với chữ ký thích hợp.
12. Vì sao cần xét receiver khi dùng `findVirtual`? **Receiver là tham số đầu trong type của method handle**, nên nó tác động tới quy tắc tiền tố.
13. Khi nào test được đánh giá? **Mỗi lần adapter được invoke**, trước khi chọn một trong hai nhánh.
14. `guardWithTest` có tự thay đổi input theo giá trị test không? **Không**; giá trị đối số được chuyển theo chữ ký gốc. Tuy vậy predicate có thể tạo side effect với object trạng thái chia sẻ.
15. Trong dự án thông thường, có nên thay mọi `if/else` bằng `guardWithTest` không? **Không**; chỉ dùng khi cần mô hình method handle compositional và có lợi ích rõ ràng.

## 14. Tài liệu đối chiếu Java SE 17

- [Java SE 17 — `MethodHandles.guardWithTest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#guardWithTest(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle)): điều kiện type của predicate, target và fallback; quy tắc chọn nhánh.
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact`, `asType`, runtime type checking.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn và so sánh chữ ký method handle.
- [Java SE 17 — `MethodHandles` combinators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `dropArguments`, `constant`, `insertArguments`, `permuteArguments`, `catchException`.
- [Java SE 17 — `SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): một loại guard có cơ chế invalidation, khác mục đích với boolean predicate tổng quát.

**Tổng kết:** `guardWithTest` không phải cơ chế tự suy diễn kiểu. Nó yêu cầu `target` và `fallback` có **cùng chính xác `MethodType`**, `test` trả **primitive `boolean`** và dùng **prefix parameters** phù hợp. Hãy **chuẩn hóa các handle trước**, kiểm tra chữ ký rồi mới ghép; khi gọi, test quyết định **một nhánh duy nhất** và lỗi của nhánh không tự được chuyển sang nhánh còn lại.