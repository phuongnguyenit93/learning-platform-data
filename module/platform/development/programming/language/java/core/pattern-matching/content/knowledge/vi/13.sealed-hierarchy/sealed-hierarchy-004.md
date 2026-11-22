# Direct subtype và final subtype trong sealed hierarchy của Java

## 1. Vì sao cần phân biệt direct subtype và final subtype?

Một **sealed hierarchy** là cây kiểu Java mà lớp hoặc interface gốc dùng từ khóa `sealed` để **kiểm soát các kiểu con trực tiếp** được phép kế thừa hay triển khai. Tính năng `sealed`/`non-sealed` trở thành chính thức từ **Java 17** (JEP 409). Từ **Java 21**, pattern matching cho `switch` (JEP 441) khai thác thông tin hệ phân cấp này để kiểm tra *exhaustiveness* (tính bao phủ nhãn `case`).

Hai khái niệm không đồng nhất:

- **Direct subtype (kiểu con trực tiếp):** kiểu được khai báo kế thừa hoặc triển khai **trực tiếp** một sealed class/interface. Với sealed parent, kiểu này phải thuộc tập được `permits` cho phép (hoặc tập được trình biên dịch suy ra khi không viết `permits`).
- **Final subtype (kiểu con đóng):** một subtype là `final` hoặc **ngầm định `final`** (như record). Kiểu đó **không thể có subclass** nữa. `final` nói về khả năng mở rộng *bản thân subtype*, không nói nó có phải subtype trực tiếp của root hay không.

Ví dụ ngắn:

```java
sealed interface Animal permits Cat, Bird {}

record Cat(String name) implements Animal {}  // Direct subtype, ngầm định final.

final class Bird implements Animal {}          // Direct subtype, tường minh final.
```

`Cat` và `Bird` đều là **direct permitted subtypes** của `Animal`; cả hai đều là **final subtypes**. Dùng `record` là cách gọn để mô hình hóa một giá trị bất biến ở tầng lá; dùng `final class` khi cần cách cài đặt lớp thông thường.

Lưu ý: ví dụ trên là **mảnh mã mô tả cấu trúc**, không phải chương trình Java có `main` độc lập. Phần 6 có chương trình đầy đủ, chạy được.

## 2. `permits` chỉ liệt kê các kiểu con trực tiếp

Xét cây kiểu:

```text
Shape  (sealed interface)
├── Circle   (record, implicitly final)
├── Polygon  (sealed interface)
│   ├── Square   (record, implicitly final)
│   └── Triangle (final class)
└── Note     (non-sealed class)
    └── SpecialNote (final class)
```

`Shape` có **ba** direct permitted subtypes: `Circle`, `Polygon`, `Note`.

- `Circle` trực tiếp `implements Shape`, nên phải được `Shape` cho phép.
- `Polygon` trực tiếp `extends Shape`, nên phải được `Shape` cho phép.
- `Note` trực tiếp `implements Shape`, nên phải được `Shape` cho phép.
- `Square` và `Triangle` trực tiếp thuộc `Polygon`, **không phải** direct subtypes của `Shape`. Chúng được quản lý bởi `Polygon permits Square, Triangle`.
- `SpecialNote` trực tiếp `extends Note`; nó vẫn là một **subtype gián tiếp** của `Shape`, nhưng **không** đưa vào `Shape permits ...` chỉ vì nó kế thừa từ `Note`.

Trong Java, quan hệ *subtype* có tính bắc cầu; nhưng `permits` chỉ nói về **cạnh kế thừa trực tiếp**. Đây là khác biệt quan trọng nhất.

### Mã khai báo tương ứng

```java
sealed interface Shape permits Circle, Polygon, Note {}

record Circle(int radius) implements Shape {}

sealed interface Polygon extends Shape permits Square, Triangle {}

record Square(int side) implements Polygon {}

final class Triangle implements Polygon {}

non-sealed class Note implements Shape {}

final class SpecialNote extends Note {}
```

Đây là **các khai báo minh họa**; khi đặt tất cả kiểu trong cùng một compilation unit/package hợp lệ thì có thể biên dịch. Ở đây chưa có phương thức `main`.

Không nên viết:

```java
// SAI về quan hệ direct subtype:
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Polygon {} // Square không trực tiếp extends/implements Shape.
```

Nếu trong `Shape permits ...` liệt kê `Square` nhưng `Square` chỉ trực tiếp triển khai `Polygon`, Java báo lỗi biên dịch: **permitted subtype được liệt kê phải trực tiếp mở rộng sealed parent**. Cũng cần khai báo `Polygon` và cho phép `Polygon` ở đúng tầng, thay vì cố gộp mọi kiểu lá vào `permits` của root.

## 3. Ba cách mà direct subtype tiếp tục một sealed hierarchy

Một class trực tiếp kế thừa sealed class hoặc trực tiếp implements sealed interface phải ở đúng một trạng thái **`final`**, **`sealed`**, hoặc **`non-sealed`**, tường minh hay ngầm định theo ngôn ngữ. Một subinterface trực tiếp mở rộng sealed interface phải là **`sealed`** hoặc **`non-sealed`** (interface không thể `final`).

| Dạng direct subtype | Khả năng mở rộng tiếp | Khi nào chọn? |
| --- | --- | --- |
| `final class C extends/implements ...` | Không thể có subclass của `C` | Kiểu lá, không cần kế thừa thêm |
| `record C(...) implements SealedInterface` | **Ngầm định final** | Kiểu lá mang dữ liệu, record phù hợp domain |
| `sealed class S ... permits ...` | Chỉ những kiểu con trực tiếp được phép | Muốn phân cấp khép kín thêm một tầng |
| `sealed interface S ... permits ...` | Chỉ những class/interface trực tiếp được phép | Muốn giới hạn các họ implementation |
| `non-sealed class N ...` | Cho phép subclass tự do theo quy tắc truy cập Java bình thường | Cần nhánh mở rộng bên ngoài tập lá đóng |
| `non-sealed interface N ...` | Cho phép interface/class tiếp tục mở rộng/triển khai | Cần một nhánh extensible của interface |

**Direct subtype không bắt buộc là final**: `Polygon` có thể được khai báo `sealed` để kiểm soát tầng tiếp theo; `Note` có thể `non-sealed` để cố ý mở rộng.

### 3.1. `final`: dừng nhánh tại kiểu đó

```java
sealed interface Payment permits Cash, Card {}

final class Cash implements Payment {}

record Card(String lastFour) implements Payment {}
```

`Cash` là `final class`; không thể viết `class SpecialCash extends Cash`. `Card` là record, vốn ngầm định `final`, nên cũng không có subclass.

`final` không có nghĩa là đối tượng **bất biến tuyệt đối**. Một final class vẫn có thể giữ trường mutable nếu thiết kế cho phép; `final` ở đây chỉ cấm **kế thừa lớp**. Record mặc định có đặc tính dữ liệu riêng (field của component là final) nhưng vẫn có thể chứa tham chiếu đến đối tượng mutable. Đừng đánh đồng ba khái niệm *final class*, *final field*, *deep immutability*.

### 3.2. `sealed`: tiếp tục khóa tầng dưới

```java
sealed interface Message permits Text, Command {}

record Text(String value) implements Message {}

sealed interface Command extends Message permits Start, Stop {}

record Start() implements Command {}

record Stop() implements Command {}
```

`Command` không phải kiểu lá: nó là **direct subtype của `Message`** và vẫn kiểm soát các kiểu trực tiếp phía dưới bằng `permits Start, Stop`.

`Start` và `Stop` không phải direct permitted subtypes của `Message`; chúng là direct permitted subtypes của `Command`. Nếu có nhiều tầng sealed, compiler kiểm tra riêng quan hệ và khai báo modifier tại mỗi tầng.

### 3.3. `non-sealed`: mở nhánh có chủ đích

```java
sealed interface Action permits BuiltIn, Extension {}

record BuiltIn(String name) implements Action {}

non-sealed interface Extension extends Action {}

final class ThirdPartyAction implements Extension {}
```

`Extension` là direct permitted subinterface của `Action` nhưng **không tiếp tục niêm phong** các implementation của chính nó. Vì vậy `ThirdPartyAction` có thể `implements Extension` mà không cần nằm trong `Action permits ...`.

`non-sealed` không có nghĩa ai cũng chắc chắn kế thừa được: các điều kiện **visibility, module, package, constructor, abstract methods** của Java vẫn áp dụng. Nó chỉ nói rằng từ tầng này trở đi không còn hạn chế do sealed modifier của chính nhánh đó.

Không được đặt `non-sealed` lên một class/interface không có **sealed direct superclass hoặc sealed direct superinterface**. Ví dụ `non-sealed class Ordinary {}` không hợp lệ chỉ vì muốn bày tỏ ý định “mở”.

## 4. Quy tắc biên dịch với direct permitted subtype

### 4.1. Được phép bởi `permits`, và phải thật sự là direct subtype

```java
sealed interface Root permits A, B {}

record A(int id) implements Root {}

final class B implements Root {}
```

Trong ví dụ này:

1. `A`, `B` là những tên kiểu được liệt kê đúng một lần trong `Root permits A, B`.
2. Cả hai thực sự trực tiếp `implements Root`.
3. `A` là record ngầm định final; `B` là final class.
4. Không có một class thứ ba `C implements Root` khi `C` không nằm trong `permits`, dù `C` có khai báo `final`.

Một lớp có keyword `final` **không tự nhận quyền** là direct subtype của sealed parent.

### 4.2. Cần `final` / `sealed` / `non-sealed`

Ví dụ cố tình sai:

```java
sealed interface Root permits Child {}

// KHÔNG HỢP LỆ: class thường chưa khai báo cách tiếp tục hierarchy.
class Child implements Root {}
```

Dù `Child` được liệt kê trong `permits`, nó vẫn phải khai báo một trong ba cách tiếp tục. Sửa:

```java
final class Child implements Root {}
```

Nếu có nhu cầu cho subclass của `Child`, có thể cân nhắc `sealed class Child ... permits ...` hoặc `non-sealed class Child ...` tùy thiết kế.

### 4.3. `final` không thể dùng đồng thời với `sealed`

Một class không thể đồng thời **`final` và `sealed`**. `final` ngăn mọi subclass; `sealed` cho phép một tập subclass trực tiếp. Tương tự, class vừa `final` vừa `abstract` là bất hợp lý vì không thể hoàn thiện bằng subclass. Dùng modifier tương ứng với mô hình domain, không ghép từ khóa theo cảm tính.

### 4.4. Interface không thể là `final`

Một direct **subinterface** của sealed interface có thể `sealed` (khóa thêm tầng) hoặc `non-sealed` (mở tầng). Interface không thể `final`. Trong khi đó, class implementing sealed interface có thể `final`, `sealed`, hoặc `non-sealed`, và record ngầm định final.

### 4.5. Quy tắc module và package

Theo JLS 17/21:

- Trong **named module**, tất cả direct permitted subtypes của một sealed class/interface phải nằm **trong cùng module** với sealed parent; có thể khác package khi quy tắc module/visibility cho phép.
- Trong **unnamed module** (trường hợp nhiều dự án Java đơn giản không khai báo module), chúng phải nằm **trong cùng package**.
- Không bắt buộc mọi type phải nằm trong **cùng file** nếu dùng `permits` tường minh và quan hệ/module/package thỏa điều kiện.

Đây là giới hạn với các **direct permitted subtypes**. Sau khi đi qua một direct `non-sealed` subtype, các subtype gián tiếp không còn bị cùng danh sách `permits` đó quản lý, dù vẫn phải tuân thủ quy định truy cập thông thường.

### 4.6. Không viết `permits` có được không?

Được, nếu compiler có thể suy ra đúng direct subtypes **trong cùng compilation unit** (cùng file nguồn) theo quy tắc JLS và các kiểu này có canonical name phù hợp. Ví dụ:

```java
sealed interface Token {}  // permits được suy ra cho Word và Numeric.

record Word(String value) implements Token {}

final class Numeric implements Token {}
```

Khi các type được tách ra nhiều file, nên khai báo `permits Word, Numeric` tường minh. Không được suy ra rằng bỏ `permits` nghĩa là cho phép mọi class cùng package implement sealed interface. Nếu không có direct permitted subtype hợp lệ để suy ra, compiler báo lỗi.

## 5. Bảng đối chiếu trực tiếp - gián tiếp - final

Xét cây `Shape → Circle, Polygon, Note → Square, Triangle, SpecialNote` ở mục 2:

| Kiểu | Direct subtype của `Shape`? | Direct subtype của `Polygon`? | `final`? | Có thể có subclass nữa? |
| --- | --- | --- | --- | --- |
| `Circle` (record) | **Có** | Không | **Có, ngầm định** | Không |
| `Polygon` (sealed interface) | **Có** | Không | Không | Chỉ direct subtype được `permits` cho phép |
| `Square` (record) | **Không** | **Có** | **Có, ngầm định** | Không |
| `Triangle` (`final class`) | Không | **Có** | **Có** | Không |
| `Note` (`non-sealed class`) | **Có** | Không | Không | Có, theo điều kiện truy cập Java |
| `SpecialNote` (`final class`) | **Không** | Không | **Có** | Không |

Vì vậy câu hỏi “`SpecialNote` có phải subtype của `Shape` không?” có đáp án **có, gián tiếp qua `Note`**; nhưng câu hỏi “`SpecialNote` có phải direct permitted subtype của `Shape` không?” có đáp án **không**. Cũng vậy, `Square` là subtype của `Shape` nhờ chuỗi `Square → Polygon → Shape`, nhưng không cần xuất hiện trong `Shape permits ...`.

**Final subtype** không mang nghĩa “mọi đường từ root đã được đóng”: nếu cây vẫn có một nhánh `non-sealed`, những subtype mới hoàn toàn có thể được tạo dưới nhánh ấy. `final` chỉ đóng **kiểu cụ thể mang modifier**.

## 6. Chương trình Java 21+ hoàn chỉnh: sealed hierarchy và `switch`

Chương trình sau sử dụng một public class chứa các kiểu lồng nhau, nên biên dịch chỉ với một file. Tất cả direct permitted subtypes được định nghĩa và kiểm soát rõ ràng. Nó minh họa:

- Hai **final leaves**: record `Circle`, record `Square`.
- Một **sealed intermediate subtype**: interface `Polygon`.
- Một **final class** trực tiếp dưới `Polygon`: `Triangle`.
- Một **non-sealed subtype**: class `Note`; và class `SpecialNote` kế thừa `Note`.
- `switch expression` Java 21 exhaustive **không có `default`**, gồm case cho các kiểu lá và `Note` mở.
- Reflection Java 17+ để liệt kê chính xác **các direct permitted subtypes**, không nhầm với mọi subtype bắc cầu.

Lưu file **`DirectFinalSubtypeDemo.java`**:

```java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DirectFinalSubtypeDemo {
    sealed interface Shape permits Circle, Polygon, Note {}

    record Circle(int radius) implements Shape {}

    sealed interface Polygon extends Shape permits Square, Triangle {}

    record Square(int side) implements Polygon {}

    static final class Triangle implements Polygon {
        private final int base;

        Triangle(int base) {
            this.base = base;
        }

        int base() {
            return base;
        }
    }

    static non-sealed class Note implements Shape {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class SpecialNote extends Note {
        SpecialNote(String text) {
            super(text);
        }
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case null -> "NULL";
            case Circle c -> "Circle(radius=" + c.radius() + ")";
            case Square s -> "Square(side=" + s.side() + ")";
            case Triangle t -> "Triangle(base=" + t.base() + ")";
            case Note n -> "Note(text=" + n.text() + ")";
        };
    }

    static String permittedNames(Class<?> type) {
        return Arrays.stream(type.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        System.out.println(classify(new Circle(2)));
        System.out.println(classify(new Square(3)));
        System.out.println(classify(new Triangle(4)));
        System.out.println(classify(new Note("memo")));
        System.out.println(classify(new SpecialNote("urgent")));
        System.out.println(classify(null));

        System.out.println("Shape permits: " + permittedNames(Shape.class));
        System.out.println("Polygon permits: " + permittedNames(Polygon.class));
        System.out.println("Circle is record: " + Circle.class.isRecord());
        System.out.println("Circle is final: "
                + Modifier.isFinal(Circle.class.getModifiers()));
        System.out.println("Polygon is sealed: " + Polygon.class.isSealed());
        System.out.println("Note is sealed: " + Note.class.isSealed());
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac DirectFinalSubtypeDemo.java
java DirectFinalSubtypeDemo
```

**Standard output mong đợi:**

```text
Circle(radius=2)
Square(side=3)
Triangle(base=4)
Note(text=memo)
Note(text=urgent)
NULL
Shape permits: Circle, Note, Polygon
Polygon permits: Square, Triangle
Circle is record: true
Circle is final: true
Polygon is sealed: true
Note is sealed: false
```

**Phân tích từng phần:**

1. `new Circle(2)` là subtype trực tiếp của `Shape`, và `Circle` là record ngầm định final, nên chọn `case Circle c`.
2. `new Square(3)` và `new Triangle(4)` là subtype **gián tiếp của `Shape` qua `Polygon`**. `case Square s` và `case Triangle t` vẫn hợp lệ vì xét kiểu runtime của `Shape`; với sealed intermediate `Polygon`, compiler có thể suy ra hai nhánh này bao phủ toàn bộ miền `Polygon`.
3. `new Note("memo")` là subtype trực tiếp được `Shape` cho phép. `new SpecialNote("urgent")` **không được liệt kê** trong `Shape permits`, nhưng hợp lệ vì kế thừa từ `Note` (`non-sealed`). Cả hai đều khớp `case Note n`, kết quả `Note(text=...)`.
4. `classify(null)` trả `NULL` vì có `case null` riêng. Pattern `Circle`, `Square`, `Triangle`, `Note` không tự khớp null.
5. Reflection `Shape.class.getPermittedSubclasses()` trả **chỉ `Circle`, `Polygon`, `Note`**, không đưa `Square`, `Triangle` hay `SpecialNote` vào tập direct permitted của `Shape`.
6. Reflection `Polygon.class.getPermittedSubclasses()` trả `Square`, `Triangle`. Hàm `permittedNames` sắp xếp tên alphabet nên đầu ra không phụ thuộc thứ tự phần tử mà API trả về.
7. `Circle.class.isRecord()` và `Modifier.isFinal(...)` đều `true` vì record là kiểu final ngầm định; `Polygon.class.isSealed()` là `true`; `Note.class.isSealed()` là `false` vì `Note` được khai báo `non-sealed`.

### Vì sao `switch` exhaustive mà không có `default`?

Trong Java 21, compiler biết `Shape` chỉ có direct permitted subtypes `Circle`, `Polygon`, `Note`. Với:

- `Circle`: đã có nhánh `case Circle`.
- `Polygon`: chính nó là sealed, chỉ cho `Square`, `Triangle`; đã có cả hai nhánh.
- `Note`: dù là `non-sealed` và có thể xuất hiện subclass tùy ý, `case Note n` khớp **cả `Note` lẫn mọi subclass của nó** (như `SpecialNote`).

Do đó các giá trị `Shape` không null đều được bao phủ mà không cần `default`. `case null` đảm bảo chính sách null minh bạch. Nếu bỏ `case Note n`, không có bộ nhánh chỉ liệt kê các subclass `SpecialNote` hiện tại nào có thể bảo đảm bao phủ tất cả subclass tương lai của `Note`.

**Cần phân biệt phiên bản:** Tính năng sealed class/interface và các API reflection về sealed đã có từ **Java 17**; `switch` với type pattern trong ví dụ là tính năng chính thức từ **Java 21**. Nếu dùng JDK 17 mà không bật preview, phần `switch (shape)` với `case Circle c` không phải cú pháp mặc định hợp lệ.

## 7. Direct subtype và tính exhaustiveness: nên đặt case ở tầng nào?

Một `switch` trên sealed root có thể chọn xử lý **tầng trực tiếp** hoặc **tầng lá**:

### 7.1. Xử lý mỗi direct permitted subtype

```java
// Mảnh switch expression hợp lệ với Shape ở ví dụ mục 6:
return switch (shape) {
    case null -> "NULL";
    case Circle c -> "circle";
    case Polygon p -> "polygon";
    case Note n -> "note";
};
```

Rule `case Polygon p` bao phủ mọi implementation của `Polygon`, bao gồm `Square` và `Triangle`. Cách này phù hợp khi nghiệp vụ chỉ cần phân loại nhóm rộng.

### 7.2. Xử lý tầng lá của sealed subtype

```java
// Mảnh switch expression dùng Shape từ mục 6:
return switch (shape) {
    case null -> "NULL";
    case Circle c -> "circle";
    case Square s -> "square";
    case Triangle t -> "triangle";
    case Note n -> "note";
};
```

Ở đây compiler truy theo nhánh `Polygon` sealed để biết `Square` và `Triangle` đã bao phủ đủ. Cách này phù hợp khi nghiệp vụ cần hành vi riêng cho từng loại polygon.

### 7.3. Không đặt case cha trước case con

```java
// KHÔNG HỢP LỆ khi đặt trong cùng switch:
case Polygon p -> "polygon";
case Square s -> "square"; // Bị nhánh Polygon che (dominance).
```

`Square` luôn là `Polygon`. Khi `case Polygon p` không guard đứng trước, `case Square s` không bao giờ được chọn, nên compiler báo lỗi nhãn bị che (*dominated case label*). Nếu cần xử lý riêng `Square`, đặt `case Square s` **trước** `case Polygon p` hoặc tách nhóm theo nhu cầu.

### 7.4. Vì sao nên cân nhắc không dùng `default` với sealed root?

Khi sealed hierarchy đóng và các case được liệt kê đầy đủ, **không có `default`** sẽ giúp compiler nhắc bổ sung nhánh khi code nguồn có direct permitted subtype mới. Ví dụ, nếu thêm một direct subtype `record Line(int length) implements Shape {}` vào `Shape permits`, các switch chỉ có các nhánh cũ không còn exhaustive sau khi biên dịch lại.

Nếu có `default`, mã có thể tiếp tục biên dịch mà logic riêng cho `Line` bị bỏ quên. Với các hệ thống/plugin cần mở rộng bằng `non-sealed`, `case Note n` vẫn cần bao phủ nhánh mở; không thể trông chờ compiler biết trước tất cả subclass của `Note`.

Lưu ý vấn đề **binary evolution**: khi hierarchy được thay đổi rồi phân phối riêng, mã switch biên dịch với tập subtype cũ có thể gặp subtype mới ở runtime và ném `java.lang.MatchException`. Vì vậy nên build/test lại toàn bộ các module liên quan khi chỉnh `permits`.

## 8. `final` ở subtype không đồng nghĩa với immutable object

Một hiểu nhầm phổ biến là `final class` đảm bảo mọi trạng thái bên trong không thể đổi:

```java
sealed interface Box permits MutableBox {}

final class MutableBox implements Box {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }
}
```

Đây là mảnh khai báo hợp lệ: `MutableBox` là **final subtype**, nhưng phương thức `increment()` vẫn có thể đổi trường `count`. Từ khóa `final` trên class chỉ nói rằng **không được kế thừa class ấy**. Nó không cấm mọi thay đổi trong phương thức.

Tương tự, một record là final và không cho gán lại component field, nhưng nếu component trỏ tới một list mutable thì nội dung list vẫn có thể đổi. Khi thiết kế domain, cần đánh giá thêm bất biến dữ liệu; `sealed` và `final` giải quyết **hình dạng cây kiểu**, không tự giải quyết tất cả vấn đề quản lý trạng thái.

## 9. Lỗi phổ biến và cách khắc phục

### 9.1. Đưa subtype gián tiếp vào `permits` root

**Sai:** `Shape permits Square` trong khi `Square implements Polygon`, còn `Polygon extends Shape`. `Square` không trực tiếp `implements Shape`; phải liệt kê `Polygon` ở root và `Square` ở `Polygon permits`.

### 9.2. Cho rằng mọi subtype của sealed root đều phải có mặt trong `permits`

`permits` chỉ liệt kê **direct subtypes**. Những subtype phía dưới một branch `sealed` hoặc `non-sealed` là **indirect subtypes** của root và không nằm trong danh sách root.

### 9.3. Quên modifier ở direct class

Một class trực tiếp `implements SealedInterface` mà chỉ viết `class C` (không final/sealed/non-sealed) sẽ gây lỗi biên dịch, trừ trường hợp các đặc tính ngôn ngữ khiến kiểu vốn **ngầm định final** (record, một số dạng enum).

### 9.4. Dùng `non-sealed` cho class thường

`non-sealed` chỉ hợp lệ khi class/interface có một sealed direct superclass hoặc superinterface tương ứng. Một subclass của `non-sealed` branch **không cần** modifier `non-sealed` và nếu không trực tiếp chịu ảnh hưởng của sealed parent thì cũng **không được** tự ghi `non-sealed`.

### 9.5. Cho rằng `final` tự cấp quyền mở rộng sealed parent

Không. Direct class vẫn phải nằm trong tập được `permits` cho phép. `final class Rogue implements Shape` khi `Rogue` không được phép là lỗi.

### 9.6. Cho rằng `final` đồng nghĩa với `sealed`

`final` cấm mọi subclass; `sealed` cho phép một số subclass được nêu rõ. Nếu cần nhiều tầng domain, dùng `sealed` cho intermediate types, `final` cho leaves.

### 9.7. Đánh đồng kiểu lá với kiểu cuối cùng của toàn cây

`Triangle` có thể `final`, nhưng nếu `Note` còn `non-sealed`, toàn bộ cây `Shape` vẫn có thể nhận thêm subtype dưới `Note`. “Mọi leaf hiện tại đều final” không đủ chứng minh toàn cây đóng.

### 9.8. Xử lý sealed switch chỉ bằng subtype gián tiếp cụ thể của nhánh mở

Nếu `Note` là `non-sealed`, việc liệt kê chỉ `SpecialNote` không bao phủ mọi `Note` và subclass tương lai. Để switch exhaustive, xử lý `case Note n` hoặc có nhánh tổng quát phù hợp.

### 9.9. Đổi thứ tự case khiến lớp con bị che

`case Polygon p` trước `case Square s` che nhánh `Square`; `case Shape s` trước bất kỳ subtype nào cũng sẽ che các subtype đó nếu dùng như pattern không guard. Đặt các nhánh chuyên biệt trước nhánh tổng quát.

### 9.10. Hiểu sai ràng buộc file/package/module

Trong unnamed module, direct permitted subtypes phải cùng package. Trong named module, cùng module, không nhất thiết cùng package. Không bắt buộc cùng file nếu `permits` tường minh; **chỉ khi muốn suy luận `permits`** thì cùng compilation unit là điều kiện quan trọng.

### 9.11. Không phân biệt Java 17 và Java 21

Dùng JDK 17+ để biên dịch sealed hierarchy. Dùng **JDK 21+** cho switch type patterns ổn định; đừng viết `case Circle c` trong switch rồi coi đó là cú pháp Java 17 mặc định.

## 10. Bài tập thực hành

1. Vẽ sealed hierarchy `Transport` có direct permitted subtypes `Car` (record), `Bike` (final class), `AirVehicle` (sealed interface) và `ExtensionTransport` (non-sealed interface). Liệt kê rõ direct/indirect subtype của `Transport`.
2. Thêm `Helicopter` và `Plane` làm direct permitted subtypes của `AirVehicle`; chọn `record` hoặc `final class` phù hợp. Giải thích vì sao hai kiểu này không cần nằm trong `Transport permits ...`.
3. Thêm `CustomTransport implements ExtensionTransport`; giải thích vì sao đây là subtype gián tiếp được phép của `Transport` nhưng không nằm trong `Transport permits`.
4. Thử khai báo `class Bike implements Transport {}` (nếu Bike nằm trong permits). Dự đoán lỗi do thiếu `final/sealed/non-sealed`, sau đó sửa thành `final class Bike`.
5. Thử thêm `final class Scooter implements Transport {}` mà không sửa `Transport permits` và giải thích lỗi compiler.
6. Viết `switch expression` Java 21 cho `Transport` theo **direct permitted subtype**: `case Car`, `case Bike`, `case AirVehicle`, `case ExtensionTransport` và `case null`. Có cần `default` không?
7. Viết lại switch của câu 6 theo **các lá** của `AirVehicle`, nhưng vẫn có `case ExtensionTransport` để bao phủ nhánh mở.
8. Cho `record Car(List<String> tags) implements Transport {}`; giải thích vì sao `Car` là final nhưng chưa chắc dữ liệu `tags` bất biến sâu.
9. Dùng `Class.getPermittedSubclasses()` để in các direct permitted types của `Transport` và `AirVehicle`, **sắp xếp tên trước khi in**. So sánh với cây subtype bắc cầu của bạn.
10. Chuyển `ExtensionTransport` từ `non-sealed` thành `sealed`, liệt kê các direct permitted children rồi biên dịch lại switch. Nêu lợi ích và chi phí khi kiểm soát sâu hơn.

**Ghi nhớ:** Sealed parent kiểm soát **direct subtype**, không liệt kê toàn bộ hậu duệ. Mỗi direct class phải chốt cách tiếp tục bằng `final`, `sealed` hoặc `non-sealed`; record là final ngầm định. **Final subtype** đóng riêng nhánh của nó, trong khi **sealed intermediate subtype** có thể mở thêm tầng được kiểm soát và **non-sealed subtype** cố ý mở một nhánh. Trong Java 21, chính những quan hệ này giúp `switch` xác định được tập `case` exhaustive.

## 11. Tài liệu tham khảo chính thức

- [JLS 21, §8.1.1.2 — Sealed, Non-sealed and Final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2).
- [JLS 21, §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6).
- [JLS 21, §9.1.1.4 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4).
- [JLS 21, §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.4).
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
