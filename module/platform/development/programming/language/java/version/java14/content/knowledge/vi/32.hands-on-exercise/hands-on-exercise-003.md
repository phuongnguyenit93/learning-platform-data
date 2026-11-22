# Mô hình dữ liệu bằng record có kiểm tra và sao chép phòng vệ

## Mục tiêu

Khi ứng dụng Java nhận dữ liệu từ API, form, message queue, database hoặc một module khác, ta thường cần một đối tượng **mang dữ liệu đã hợp lệ và không bị thay đổi ngoài ý muốn** sau khi tạo. Một `record` rất phù hợp cho loại mô hình này, nhưng cần hiểu rằng **record chỉ bất biến ở mức tham chiếu của các component, không tự bất biến sâu**.

Ví dụ, bản ghi `record Order(List<Line> lines) {}` có field `lines` là `final`, nhưng nếu bên ngoài vẫn giữ `ArrayList` truyền vào thì họ có thể sửa danh sách và làm nội dung `Order` thay đổi. Một bản ghi `record Blob(byte[] bytes) {}` còn nguy hiểm hơn: mảng có thể bị sửa cả **trước khi đưa vào constructor** và **sau khi lấy qua accessor**. Vì vậy, mô hình dữ liệu vững chắc cần kết hợp **record + kiểm tra đầu vào + chuẩn hóa + defensive copying đúng độ sâu + kiểm thử invariants**.

Bài thực hành tập trung vào các kỹ năng:

1. Chọn `record` khi mô hình là một **data carrier có tập component cố định**.
2. Viết **compact canonical constructor** để validate và chuẩn hóa arguments.
3. Phân biệt **validation về kiểu**, **validation nghiệp vụ** và **kiểm tra tràn số**.
4. Sao chép phòng vệ collections với `List.copyOf`/`Map.copyOf`, hiểu hành vi từ chối `null`.
5. Sao chép primitive arrays ở **đầu vào constructor** và **đầu ra accessor**.
6. Hiểu **shallow copy** không đóng băng đối tượng mutable nằm bên trong `List`/`Map`.
7. Chuyển mutable DTO thành các immutable record components bằng một bước **snapshot từng phần tử**.
8. Xử lý `equals`, `hashCode` và `toString` khi record chứa mảng.
9. Kiểm thử cả **giá trị đã được giữ ổn định**, **cố ý sửa dữ liệu từ bên ngoài**, **đầu vào không hợp lệ** và **bất biến của record**.
10. Biên dịch và chạy một chương trình Java 17+ đầy đủ; biết các mốc phiên bản để không lẫn preview Java 14 với cú pháp chính thức hiện nay.

**Phiên bản:** Records được giới thiệu ở **Java 14 dưới dạng preview** (JEP 359), tiếp tục preview tại Java 15 (JEP 384), và trở thành **tính năng chính thức ở Java 16** (JEP 395). Bài viết dùng **cú pháp Java 17+ đã ổn định**, biên dịch không cần `--enable-preview`. `List.copyOf` và `Map.copyOf` có từ Java 10, vẫn dùng bình thường trong JDK hiện hành. Không dùng các cú pháp preview cũ hoặc mẹo nội bộ để giả lập bất biến.

## 1. Record mang lại gì, và không mang lại gì?

Một record rất ngắn:

~~~java
record Point(int x, int y) {}
~~~

Java tự tạo các thành phần cơ bản:

- Hai **private final component fields** tương ứng `x` và `y`.
- **Canonical constructor** nhận tham số `int x, int y`.
- Accessors công khai `x()` và `y()`, **không tự sinh theo mẫu JavaBean `getX()`**.
- `equals(Object)` so sánh các components theo hợp đồng của record.
- `hashCode()`, `toString()` dựa trên components.
- Record class có tính `final`, ngầm kế thừa `java.lang.Record`; không thể mở rộng một class ứng dụng khác, nhưng có thể implements interfaces.

Ví dụ:

~~~java
Point p = new Point(3, 4);
System.out.println(p.x());                   // 3
System.out.println(p.y());                   // 4
System.out.println(p.equals(new Point(3, 4))); // true
~~~

Record phù hợp với các đối tượng như `Coordinate`, `Money`, `OrderLine`, `DateRange`, `SearchQuery`, `AuditEntry` hay snapshot kết quả tính toán. **Không nhất thiết** phù hợp nếu đối tượng có identity riêng và nhiều state transitions như một entity có lifecycle phức tạp.

### 1.1. Bất biến nông, không phải bất biến sâu

Xem một record **cố ý thiếu defensive copy**:

~~~java
import java.util.List;

// Mẫu thiếu bảo vệ, không dùng nguyên trạng cho dữ liệu cần bất biến.
record UnsafeBasket(List<String> items) {}
~~~

Có thể xảy ra:

~~~java
List<String> source = new java.util.ArrayList<>();
source.add("PEN");
UnsafeBasket basket = new UnsafeBasket(source);

source.add("PAPER");
System.out.println(basket.items().size()); // 2, dù basket đã tạo trước!
~~~

`items` là một **final reference** nhưng vẫn trỏ tới `ArrayList` có thể bị sửa. `final` bảo đảm **không gán lại field**, không khóa mọi method bên trong đối tượng tham chiếu.

Với `byte[]`, vấn đề cũng tương tự:

~~~java
record UnsafeBytes(byte[] data) {}

byte[] source = {1, 2};
UnsafeBytes value = new UnsafeBytes(source);
source[0] = 99;      // Thay dữ liệu "bên trong" record.
value.data()[1] = 88; // Accessor còn làm lộ mảng gốc.
~~~

Đây là lý do câu “record tự động immutable” **không chính xác**. Javadoc gọi record là **shallowly immutable**: tham chiếu các components được cố định, còn đối tượng được tham chiếu có thể mutable.

## 2. Các loại kiểm tra cần có ở ranh giới dữ liệu

Với một dòng đơn hàng, ta có thể muốn bảo đảm:

- `sku` **không null** và **không rỗng sau khi chuẩn hóa**.
- `quantity` phải **lớn hơn 0**.
- `unitPriceCents` phải **không âm** theo quy tắc mẫu.
- Tiền được lưu bằng `long` tính theo **đơn vị nhỏ nhất**, tránh dùng `double` để chứa giá tiền dạng thập phân.
- Tích `quantity × unitPriceCents` phải được tính **không âm thầm overflow**.
- Quy tắc currency, tax, discounts, max order size nếu có phải được kiểm tra **riêng**, không phải do record tự động xử lý.

Một cách thực hiện:

~~~java
import java.util.Objects;

// Đoạn minh họa: đặt bên trong một source file Java phù hợp.
record Line(String sku, int quantity, long unitPriceCents) {
    Line {
        sku = Objects.requireNonNull(sku, "sku").strip();

        if (sku.isEmpty() || quantity <= 0 || unitPriceCents < 0) {
            throw new IllegalArgumentException("invalid line");
        }
    }

    long subtotalCents() {
        return Math.multiplyExact((long) quantity, unitPriceCents);
    }
}
~~~

`Objects.requireNonNull` tạo lỗi rõ khi tham số `sku` là `null`. `strip()` chuẩn hóa khoảng trắng ở hai đầu (Java 11+) nhưng không tự chuẩn hóa case/Unicode/cấu trúc mã hàng. `IllegalArgumentException` được dùng cho **validation nghiệp vụ**.

`Math.multiplyExact((long) quantity, unitPriceCents)` từ chối kết quả vượt `long` bằng `ArithmeticException`. **Không chỉ gán một phép nhân int vào long sau khi nhân**, vì overflow có thể đã xảy ra. Trong ví dụ này `unitPriceCents` vốn là `long`, nên cast `(long) quantity` làm ý định rõ ràng; kết quả toán học vẫn phải được kiểm tra.

**Quan trọng:** Một record hợp lệ về kiểu primitive vẫn có thể sai về nghiệp vụ. Java không tự biết rằng một `quantity == 0` phải bị cấm; **compact constructor** là nơi diễn đạt invariant.

## 3. Canonical constructor và compact canonical constructor

Record có đúng một **canonical constructor** tương ứng với danh sách components. Có hai kiểu khai báo rõ ràng.

### 3.1. Constructor đầy đủ

~~~java
record UserId(String value) {
    public UserId(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
        this.value = value.strip();
    }
}
~~~

Ở đây `UserId` là **package-private record**, còn canonical constructor `public` có access không hẹp hơn record, nên hợp lệ. Với record `public`, canonical constructor phải có visibility phù hợp, thường là `public`.

Constructor đầy đủ **phải tự gán** mọi component field theo luật definite assignment. Nó hữu ích khi cần viết logic phức tạp, nhưng lặp tên tham số và dễ gây sai khi thêm component.

### 3.2. Compact constructor

~~~java
record UserId(String value) {
    UserId {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank id");
        }
    }
}
~~~

Trong `UserId { ... }`:

1. Các tham số `value` được **khai báo ngầm** theo record header.
2. Bạn có thể **kiểm tra và gán lại tham số** `value` để chuẩn hóa.
3. Khi thân compact constructor kết thúc bình thường, Java **tự gán tham số đã chuẩn hóa** vào private final component field tương ứng.
4. **Không được trực tiếp gán `this.value`** trong compact constructor; JLS xem đó là compile-time error.
5. Compact constructor cũng **không được viết `return;`** để bỏ qua một bước kiểm tra.

**Ví dụ cố ý sai:**

~~~java
// KHÔNG BIÊN DỊCH: gán trực tiếp component field trong compact constructor.
record BadId(String value) {
    BadId {
        this.value = value.strip(); // Không hợp lệ.
    }
}
~~~

**Sửa:** gán lại tham số `value = value.strip();`, rồi để compiler tạo assignment cuối constructor.

### 3.3. Invariant không chỉ là điều kiện if

Một invariant tốt có thể gồm:

- **Not-null:** tham số/reference components không null.
- **Range:** `quantity > 0`, `price >= 0`, `from <= to`.
- **Normalization:** `strip()`, chuẩn hóa mã, thống nhất timezone/units theo chính sách.
- **Cross-component:** tổng số lượng không vượt quota, ngày bắt đầu không sau ngày kết thúc.
- **Safe representation:** defensive copy trước khi component final được gán.
- **Consistency:** những method như `subtotalCents()` phải xử lý overflow thay vì âm thầm wrap.

**Không lạm dụng:** Việc ném exception trong constructor là hợp lý khi dữ liệu không có cách diễn giải hợp lệ. Nếu input của user thường xuyên sai, ứng dụng nên validate ở API/UI boundary và trả lỗi có cấu trúc; không dựa vào stack trace là UX.

## 4. Defensive copying của List và Map

Với các record components là collections:

~~~java
record Order(String id, List<Line> lines, Map<String, String> tags) {
    Order {
        id = Objects.requireNonNull(id, "id").strip();

        if (id.isEmpty()) {
            throw new IllegalArgumentException("blank order id");
        }

        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("empty order");
        }

        tags = Map.copyOf(tags);
    }
}
~~~

`List.copyOf` và `Map.copyOf` trả collections **unmodifiable**, biểu diễn một **snapshot của membership/entries** tại thời điểm tạo. Khi nguồn thay đổi danh sách hoặc map về sau, contents của collection được trả ra **không tự đổi theo**.

Ví dụ:

~~~java
List<Line> sourceLines = new ArrayList<>();
sourceLines.add(new Line("PEN", 2, 150));

Map<String, String> sourceTags = new HashMap<>();
sourceTags.put("source", "web");

Order order = new Order("ORD-7", sourceLines, sourceTags);
sourceLines.clear();
sourceTags.put("source", "mobile");

// order vẫn chứa line đã chụp và sourceTag "web".
~~~

### 4.1. Các bảo đảm đúng của copyOf

| Tiêu chí | `List.copyOf` | `Map.copyOf` |
|---|---|---|
| Kết quả sửa bằng `add`/`remove`/`put` được không? | Không, `UnsupportedOperationException` | Không, `UnsupportedOperationException` |
| Nguồn thay đổi cấu trúc sau này làm snapshot đổi? | Không | Không |
| Chấp nhận collection đầu vào `null`? | Không, `NullPointerException` | Không, `NullPointerException` |
| Chấp nhận phần tử `null`? | Không | Không nhận key/value `null` |
| Giữ thứ tự? | Theo iteration order của collection đầu vào | **Không bảo đảm iteration order cố định** |
| Tự copy sâu các object bên trong? | **Không** | **Không** |
| Bảo đảm cấp phát một instance mới mỗi lần? | **Không**; có thể tái dùng unmodifiable collection | **Không**; có thể tái dùng unmodifiable map |

**Điểm tinh tế:** `copyOf` được gọi là “copy” vì bảo đảm snapshot theo nội dung, **không có nghĩa luôn tạo object List/Map có identity khác**. Nếu nguồn đã là unmodifiable implementation phù hợp, JDK có thể trả lại chính object đó. Vì vậy đừng dùng `source != copy` làm tiêu chí QA.

### 4.2. Vì sao không chỉ Collections.unmodifiableList?

~~~java
List<String> backing = new ArrayList<>();
backing.add("PEN");

List<String> view = Collections.unmodifiableList(backing);
backing.add("PAPER");

System.out.println(view.size()); // 2
~~~

`Collections.unmodifiableList(backing)` tạo **view không thể sửa qua view**, nhưng vẫn thấy mutations của **backing list**. Nó **không phải snapshot**.

Muốn snapshot, dùng:

~~~java
List<String> safe = List.copyOf(backing);
~~~

Sau khi tạo, thay đổi về membership của `backing` không làm `safe` đổi. Nếu các phần tử bên trong mutable, cần xử lý riêng theo mục 5.

### 4.3. List.of, Arrays.asList, unmodifiable và immutable khác nhau

- `List.of(...)` tạo unmodifiable list từ các phần tử được cung cấp, không chấp nhận null.
- `List.copyOf(collection)` tạo snapshot membership của một collection có sẵn.
- `Arrays.asList(array)` tạo **fixed-size list backed by array**; `set` có thể sửa element và các thay đổi trên mảng backing có thể phản ánh vào list.
- `Collections.unmodifiableList(list)` trả unmodifiable **view**, không đảm bảo snapshot của backing list.
- Cả `List.of` và `List.copyOf` **không tự đông cứng mỗi object phần tử**.

Hãy phân biệt **unmodifiable collection** (không thay số phần tử/entry qua API collection) với **deeply immutable object graph** (không có node bên trong nào đổi được theo những tham chiếu bên ngoài).

## 5. Shallow copy vẫn có thể để lọt mutation của phần tử

Giả sử data source cung cấp một DTO mutable:

~~~java
static final class MutableLine {
    String sku;
    int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}
~~~

Và record chỉ snapshot danh sách:

~~~java
record ShallowGroup(List<MutableLine> items) {
    ShallowGroup {
        items = List.copyOf(items);
    }
}
~~~

Sau khi tạo record, thao tác:

~~~java
MutableLine line = new MutableLine("PEN", 2);
List<MutableLine> source = new ArrayList<>();
source.add(line);

ShallowGroup group = new ShallowGroup(source);
source.clear();          // Record vẫn giữ 1 phần tử.
line.quantity = 99;      // Nhưng chính phần tử đó vẫn mutable!

System.out.println(group.items().get(0).quantity); // 99
~~~

**Vì sao?** `List.copyOf` sao chép membership, **không clone `MutableLine`**. Dù bạn không thể `group.items().add(...)`, bạn vẫn có thể sửa object mà list chứa nếu có tham chiếu tới nó.

### 5.1. Chuyển DTO thành immutable record values

Dùng một record cho phần tử snapshot:

~~~java
record FrozenLine(String sku, int quantity) {}
record FrozenGroup(List<FrozenLine> items) {
    FrozenGroup {
        items = List.copyOf(items);
    }

    static FrozenGroup fromMutable(List<MutableLine> source) {
        Objects.requireNonNull(source, "source");
        List<FrozenLine> result = new ArrayList<>();

        for (MutableLine line : source) {
            Objects.requireNonNull(line, "line");
            result.add(new FrozenLine(line.sku, line.quantity));
        }
        return new FrozenGroup(result);
    }
}
~~~

Ở đây constructor `FrozenLine(String,int)` nhận các thành phần **String và int đều immutable theo cách dùng ví dụ**; copy tạo **đối tượng con mới** thay vì giữ nguyên `MutableLine`. Khi `line.quantity` ở nguồn đổi, `FrozenLine.quantity()` vẫn giữ giá trị cũ.

**Cần làm thêm ở production:** Mẫu `FrozenLine` chỉ minh họa sao chép. Để là domain model an toàn thật sự, thêm validation trong constructor (`sku` không blank, `quantity > 0`), không sao chép trực tiếp các nested mutable references và định nghĩa chính sách xử lý null/duplicate rõ ràng.

### 5.2. Deep copy nghĩa là đến mức nào?

Không có một công thức `clone()` chung cho mọi object graph. Khi record có:

~~~java
record Report(Map<String, List<MutableLine>> groups) {}
~~~

`Map.copyOf(groups)` **chỉ cố định các entries của map**. Các list values và từng `MutableLine` vẫn mutable. Muốn một snapshot bền vững:

1. Tạo một map đích mới.
2. Với từng entry, tạo list đích mới.
3. Với từng element, chuyển thành immutable value record và validate.
4. Đóng băng từng list bằng `List.copyOf`.
5. Đóng băng map bằng `Map.copyOf`.
6. Không giữ lại bất kỳ mutable reference nào dẫn tới phần state phải bất biến.

**Không bắt buộc deep copy mọi thứ:** Nếu leaf value đã immutable như `String`, `Integer`, `BigDecimal`, `LocalDate` hoặc record đã được thiết kế immutable sâu, việc tạo lại toàn bộ đối tượng có thể không cần thiết. Chọn độ sâu copy theo **đường dẫn có thể bị mutate từ bên ngoài** và hợp đồng của domain.

## 6. Với mảng: cần sao chép cả lúc nhận và trả

Primitive arrays như `byte[]` hoặc `int[]` có thể bị sửa ngay cả khi field chứa chúng là `final`.

Một record sai:

~~~java
record RawPayload(byte[] bytes) {}
~~~

Hai hướng bị lộ:

- **Tại constructor:** `byte[] source` do caller giữ; nếu chỉ gán vào record, caller sửa `source[0]` là sửa dữ liệu được record thấy.
- **Tại accessor:** accessor tự sinh `bytes()` trả **chính mảng field**; caller có thể gọi `payload.bytes()[0] = 99`.

Mẫu chuẩn:

~~~java
import java.util.Arrays;
import java.util.Objects;

record Blob(byte[] bytes) {
    Blob {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Blob that
                && Arrays.equals(bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return "Blob[length=" + bytes.length + "]";
    }
}
~~~

**Giải thích:**

1. `bytes = bytes.clone();` trong **compact constructor** sao chép khi nhận.
2. Compiler sau đó gán array đã clone vào component field `final`.
3. Accessor `bytes()` trả **một clone mới** khi caller yêu cầu đọc.
4. `equals/hashCode` dùng `Arrays.equals/Arrays.hashCode` vì đối tượng `byte[]` **không có value-equality** mặc định.
5. `toString()` chỉ in độ dài, tránh in toàn bộ payload nhị phân hoặc một chuỗi định danh mảng vô nghĩa.

### 6.1. Vì sao hai lần clone đều cần thiết?

Nếu chỉ clone **constructor**, accessor vẫn làm lộ private array. Nếu chỉ clone **accessor**, người gọi còn giữ array truyền vào constructor và sửa được state trước mỗi lần đọc.

Đối với mảng chứa dữ liệu bí mật, clone chỉ hỗ trợ **encapsulation**, không phải một cơ chế mã hóa hoặc xóa sạch memory; thiết kế security phải xem xét cách cấp phát và lifetime của các bản sao.

### 6.2. Arrays.equals vs equality của record

Với:

~~~java
record BareBlob(byte[] bytes) {}

BareBlob a = new BareBlob(new byte[]{1, 2, 3});
BareBlob b = new BareBlob(new byte[]{1, 2, 3});

System.out.println(a.equals(b)); // false
~~~

Hai mảng có nội dung giống hệt nhưng **hai tham chiếu khác nhau**, nên phương thức `equals` tự sinh của record sẽ so sánh component reference type theo hợp đồng tương đương `Objects.equals`, và `byte[]` mặc định chỉ có reference equality.

Nếu muốn **semantic equality theo byte content**, phải **override cả equals và hashCode** giống `Blob`. Chỉ override `equals` mà không override `hashCode` sẽ vi phạm hợp đồng Java khi dùng record làm key trong `HashMap`/`HashSet`.

**Một hướng thiết kế khác:** biểu diễn payload dưới dạng immutable value abstraction có semantics rõ, thay vì đưa raw array vào header của record. Tuy nhiên, nếu dùng `ByteBuffer`, hãy kiểm tra liệu nó có writable view hay backing array bị lộ; `asReadOnlyBuffer()` không đồng nghĩa một bản sao bất biến sâu của backing bytes.

### 6.3. Record copy-equals invariant

Javadoc của `java.lang.Record` yêu cầu: nếu tạo một record mới bằng các kết quả accessors của record cũ, record mới phải **equal** với record cũ.

Khái niệm:

~~~java
// Đoạn minh họa chung.
R copy = new R(r.component1(), r.component2());
assert r.equals(copy);
~~~

Đây là **pseudo-code về invariant**, không thể biên dịch với type `R` nếu chưa khai báo một record thật. Với record chứa mảng, nếu accessor clone mảng nhưng để `equals` mặc định so sánh identity của mảng, invariant có thể bị phá. Chính vì vậy `Blob` cần `Arrays.equals` và `Arrays.hashCode` phù hợp.

Với một record gồm `List<Line>` và `Map<String,String>` đã copy vào immutable values, các phương thức `equals/hashCode` tự sinh thông thường cho semantics giá trị hợp lý.

## 7. Chương trình Java 17 hoàn chỉnh, có thể chạy

Bài thực hành kết hợp **4 vấn đề** trong một chương trình:

- `Line`: validate từng component và kiểm tra overflow khi tính subtotal.
- `Order`: chuẩn hóa ID, snapshot `List`/`Map` và cộng tổng an toàn.
- `Blob`: copy mảng tại constructor/accessor; equality/hash theo nội dung.
- `ShallowGroup` và `FrozenGroup`: chứng minh copy collection nông và cách chụp từng element mutable.

### 7.1. Tệp RecordDefensiveCopyDemo.java

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class RecordDefensiveCopyDemo {
    record Line(String sku, int quantity, long unitPriceCents) {
        Line {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty() || quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long subtotalCents() {
            return Math.multiplyExact((long) quantity, unitPriceCents);
        }
    }

    record Order(String id, List<Line> lines, Map<String, String> tags) {
        Order {
            id = Objects.requireNonNull(id, "id").strip();
            if (id.isEmpty()) {
                throw new IllegalArgumentException("blank order id");
            }
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("empty order");
            }
            tags = Map.copyOf(tags);
        }

        long totalCents() {
            long total = 0;
            for (Line line : lines) {
                total = Math.addExact(total, line.subtotalCents());
            }
            return total;
        }
    }

    record Blob(byte[] bytes) {
        Blob {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Blob that
                    && Arrays.equals(bytes, that.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }

        @Override
        public String toString() {
            return "Blob[length=" + bytes.length + "]";
        }
    }

    record BareBlob(byte[] bytes) {}

    static final class MutableLine {
        String sku;
        int quantity;

        MutableLine(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }
    }

    record ShallowGroup(List<MutableLine> items) {
        ShallowGroup {
            items = List.copyOf(items);
        }
    }

    record FrozenLine(String sku, int quantity) {}

    record FrozenGroup(List<FrozenLine> items) {
        FrozenGroup {
            items = List.copyOf(items);
        }

        static FrozenGroup fromMutable(List<MutableLine> source) {
            Objects.requireNonNull(source, "source");
            List<FrozenLine> result = new ArrayList<>();
            for (MutableLine line : source) {
                Objects.requireNonNull(line, "line");
                result.add(new FrozenLine(line.sku, line.quantity));
            }
            return new FrozenGroup(result);
        }
    }

    static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=NO_EXCEPTION");
        } catch (IllegalArgumentException | NullPointerException
                 | UnsupportedOperationException ex) {
            System.out.println(
                    label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<Line> inputs = new ArrayList<>();
        inputs.add(new Line("  PEN ", 2, 150));

        Map<String, String> tags = new HashMap<>();
        tags.put("source", "web");

        Order order = new Order("  ORD-7  ", inputs, tags);
        inputs.add(new Line("PAPER", 1, 100));
        tags.put("source", "changed");

        System.out.println("orderId=" + order.id());
        System.out.println("lineCount=" + order.lines().size());
        System.out.println("sourceTag=" + order.tags().get("source"));
        System.out.println("totalCents=" + order.totalCents());
        System.out.println("equalOrders=" + order.equals(
                new Order("ORD-7", List.of(new Line("PEN", 2, 150)),
                        Map.of("source", "web"))));

        check("mutateList",
                () -> order.lines().add(new Line("X", 1, 1)));
        check("mutateMap",
                () -> order.tags().put("source", "mobile"));
        check("blankId",
                () -> new Order(" ",
                        List.of(new Line("PEN", 1, 1)), Map.of()));
        check("zeroQuantity",
                () -> new Line("PEN", 0, 100));
        check("nullElement",
                () -> new Order("ok",
                        Arrays.asList((Line) null), Map.of()));

        byte[] original = {1, 2, 3};
        Blob blob = new Blob(original);
        original[0] = 99;
        byte[] leaked = blob.bytes();
        leaked[1] = 88;

        System.out.println("blobBytes=" + Arrays.toString(blob.bytes()));
        System.out.println("blobEqual=" +
                blob.equals(new Blob(new byte[]{1, 2, 3})));
        System.out.println("blobHashEqual=" + (blob.hashCode()
                == new Blob(new byte[]{1, 2, 3}).hashCode()));
        System.out.println("bareBlobEqual=" +
                new BareBlob(new byte[]{1, 2, 3})
                        .equals(new BareBlob(new byte[]{1, 2, 3})));
        System.out.println("blobToString=" + blob);

        MutableLine shared = new MutableLine("PEN", 2);
        List<MutableLine> mutableInput = new ArrayList<>();
        mutableInput.add(shared);

        ShallowGroup shallow = new ShallowGroup(mutableInput);
        FrozenGroup frozen = FrozenGroup.fromMutable(mutableInput);

        mutableInput.clear();
        shared.quantity = 99;

        System.out.println("shallowQuantity=" +
                shallow.items().get(0).quantity);
        System.out.println("frozenQuantity=" +
                frozen.items().get(0).quantity());
    }
}
~~~

### 7.2. Biên dịch và chạy

JDK 17+ (Bash hoặc terminal có `javac`/`java` trong `PATH`):

~~~bash
javac --release 17 -encoding UTF-8 RecordDefensiveCopyDemo.java
java RecordDefensiveCopyDemo
~~~

**Đầu ra đã được kiểm chứng bằng Java 17 source level:**

~~~text
orderId=ORD-7
lineCount=1
sourceTag=web
totalCents=300
equalOrders=true
mutateList=UnsupportedOperationException
mutateMap=UnsupportedOperationException
blankId=IllegalArgumentException
zeroQuantity=IllegalArgumentException
nullElement=NullPointerException
blobBytes=[1, 2, 3]
blobEqual=true
blobHashEqual=true
bareBlobEqual=false
blobToString=Blob[length=3]
shallowQuantity=99
frozenQuantity=2
~~~

### 7.3. Đọc kết quả như một bộ kiểm thử invariants

**Nhóm Order:**

- `orderId=ORD-7`: constructor chuẩn hóa whitespace ở `id`.
- `lineCount=1`: sau khi tạo record, list đầu vào bị thêm một dòng mới nhưng `Order.lines` vẫn giữ **snapshot lúc tạo**.
- `sourceTag=web`: map nguồn được sửa thành `changed`, record vẫn giữ value cũ.
- `totalCents=300`: `2 × 150`, tính bằng checked arithmetic.
- `equalOrders=true`: two records có components theo giá trị tương đương; các thành phần `List<Line>` và `Map<String,String>` đều có equality đúng với nhu cầu.

**Nhóm mutation không được phép:**

- `mutateList` và `mutateMap` đều ném `UnsupportedOperationException` vì accessor trả unmodifiable collections.
- `blankId` và `zeroQuantity` ném `IllegalArgumentException` vì vi phạm domain rules.
- `nullElement` ném `NullPointerException` từ `List.copyOf` vì list chứa một null element.

**Nhóm Blob:**

- `blobBytes=[1, 2, 3]`: sửa mảng nguồn và sửa một bản sao do accessor trả về **không thay đổi state thật**.
- `blobEqual=true` và `blobHashEqual=true`: equality/hash dựa trên byte content.
- `bareBlobEqual=false`: auto-generated record equality không so sánh nội dung hai mảng khác tham chiếu.
- `blobToString=Blob[length=3]`: override giúp không in payload/raw array.

**Nhóm deep copy:**

- `shallowQuantity=99`: list đã copy membership nhưng giữ cùng `MutableLine`; mutating element thay đổi state được quan sát.
- `frozenQuantity=2`: factory tạo một `FrozenLine` record mới từ giá trị lúc snapshot; thay đổi DTO đầu vào sau đó không tác động tới frozen value.

**Ranh giới kiểm chứng:** Đây là kiểm thử minh họa semantics của record/collections/arrays. Nó **không chứng minh ứng dụng an toàn với mọi concurrent write hoặc dữ liệu mạng không tin cậy**. Một production model còn cần validation theo domain và kiểm thử dưới các điều kiện phù hợp.

## 8. Thiết kế lỗi và thứ tự kiểm tra đầu vào

### 8.1. Mở rộng các bất biến ở hai cấp

`Line` có trách nhiệm bảo đảm **một dòng** hợp lệ: SKU, quantity, price. `Order` có trách nhiệm bảo đảm **một đơn hàng** hợp lệ: ID, list không trống, bản sao bảo vệ của collections.

Tránh lặp toàn bộ validation nội bộ `Line` trong `Order` khi mọi phần tử thật sự đã là immutable `Line`. Nhưng nếu `Order` có quy tắc tổng (số dòng tối đa, tổng không vượt limit, mã SKU không trùng nhau), đó là **invariant cấp Order** và nên được kiểm tra tại boundary phù hợp.

Ví dụ quy tắc tổng không vượt long:

~~~java
// Đoạn minh họa bên trong method của Order.
long total = 0;
for (Line line : lines) {
    total = Math.addExact(total, line.subtotalCents());
}
~~~

Nếu một phép nhân/cộng vượt `long`, chương trình ném `ArithmeticException`. Trong API công khai, bạn có thể chuyển lỗi này thành thông điệp domain thích hợp, nhưng **không nên âm thầm dùng giá trị đã tràn**.

### 8.2. Nên kiểm tra null trước hay sau copy?

Một số APIs copy đã validate null:

~~~java
lines = List.copyOf(lines);  // NPE nếu list hoặc element null.
tags = Map.copyOf(tags);     // NPE nếu map hoặc key/value null.
~~~

Bạn có thể dùng `Objects.requireNonNull(lines, "lines")` trước khi copy để thông điệp lỗi rõ hơn, nhưng điều đó **không thay thế** việc kiểm tra null **nằm trong collection**. Nếu business rule muốn biểu diễn dữ liệu thiếu bằng một exception khác, xử lý rõ ràng tại boundary.

**Đừng che NPE một cách tùy tiện:** NPE từ dữ liệu API có thể cần chuyển thành lỗi HTTP 400 với thông điệp/field path, nhưng bắt mọi `NullPointerException` trong code có thể che lỗi lập trình. Thiết kế error handling phù hợp nguồn dữ liệu.

### 8.3. Chuẩn hóa không được gây bất ngờ

`strip()` thay đổi giá trị `"  PEN "` thành `"PEN"`. Với mã sản phẩm, nếu business rule yêu cầu giữ whitespace hoặc phân biệt chữ hoa/chữ thường, đừng tự strip/uppercase mà không có đặc tả.

Với `String`, immutable value giúp tránh aliasing, nhưng **normalization còn là quyết định nghiệp vụ**. Với `BigDecimal`, so sánh và scale/rounding cũng cần chính sách rõ khi dùng làm số tiền.

## 9. Một số lựa chọn mô hình hóa khác

### 9.1. Chọn record components là immutable types

Ưu tiên:

~~~java
record Period(java.time.LocalDate from, java.time.LocalDate to) {
    Period {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (from.isAfter(to)) {
            throw new IllegalArgumentException("from > to");
        }
    }
}
~~~

`LocalDate` immutable; không cần clone như `java.util.Date`. Nếu dùng `Date`/`Calendar` hoặc mutable legacy types trong một record, bạn sẽ cần defensive copying ở cả constructor/accessor hoặc chuyển đổi sớm sang Java Time types.

### 9.2. Record với tập hợp khác

- `Set.copyOf` cung cấp unmodifiable set snapshot, nhưng nếu dữ liệu có **trùng lặp** thì semantics của set loại bỏ duplicate; bạn nên kiểm tra trước nếu không được phép trùng.
- `Map.copyOf` không bảo đảm iteration order giống nguồn; nếu thứ tự là một phần contract (ví dụ xuất CSV), phải chọn representation có thứ tự rõ ràng.
- `List.copyOf` giữ iteration order; phù hợp cho thứ tự các order lines.
- Nếu input là `Map<String, List<Line>>`, copy map **không deep-copy các list values**; cần copy từng list trước khi đóng băng outer map.

### 9.3. Record có component là mutable object

~~~java
// CỐ Ý THIẾU DEFENSIVE COPY:
record WrongTime(java.util.Date createdAt) {}
~~~

Ngay cả khi `createdAt` là final field, một caller có thể gọi `setTime(...)` trên đối tượng `Date` gốc hoặc đối tượng do accessor trả ra. Để tránh complexity, cân nhắc dùng `Instant` hoặc `LocalDateTime` với quy tắc timezone rõ ràng.

### 9.4. Không dùng record nếu mục tiêu là đối tượng stateful có identity và mutating lifecycle

Một entity có các chuyển trạng thái như `DRAFT → APPROVED → SHIPPED`, có identity riêng và invariants phụ thuộc transaction có thể không nên được ép thành một record mutable. Record rất phù hợp để biểu diễn **snapshot** của entity tại một thời điểm, DTO output hoặc value objects, trong khi aggregate/entity logic có thể nằm ở class/service khác.

“Record” không tự đồng nghĩa “database row” hay “ORM entity” với lazy-loading. Kiểm tra compatibility của serializer/ORM/framework cụ thể trước khi dùng record làm persistence model.

## 10. equals, hashCode và toString: khi nào đủ, khi nào cần override?

### 10.1. Trường hợp tự sinh là hợp lý

~~~java
record Line(String sku, int quantity, long priceCents) {}
~~~

Nếu `String` và primitives giữ giá trị ổn định, auto-generated `equals/hashCode` phù hợp để so sánh theo contents. Hai `Line("PEN",2,150)` có value-equality.

### 10.2. Trường hợp array cần rõ semantics

~~~java
record RawBytes(byte[] data) {}
~~~

Hai `RawBytes` được tạo từ hai mảng có bytes bằng nhau không tự bằng nhau theo value semantics. Không nghĩ record sẽ tự gọi `Arrays.equals` thay bạn.

Nếu override `equals(Object)` theo `Arrays.equals`, **phải override `hashCode()` theo cùng contents**, và thực hiện defensive copy để giữ hash code ổn định sau khi record được dùng làm key trong `HashMap`. Hash code thay đổi do một mảng bị mutate là một lỗi logic rất khó debug.

### 10.3. Auto toString có thể làm lộ dữ liệu

`toString()` tự sinh có thể chứa giá trị các components. Nếu record có token, thông tin cá nhân, credential, giá tiền nhạy cảm hoặc nội dung payload, **không đưa toàn bộ record vào log** khi không có chính sách redaction. Override `toString()` hoặc dùng logger có cấu trúc với allowlist fields.

Với array, generated `toString` thường không hữu ích để đọc bytes (ví dụ định danh array). `Blob.toString()` minh họa cách chỉ in chiều dài.

### 10.4. Bảo toàn record copy-equals

Với một record có thể kiểm tra invariants, Javadoc `java.lang.Record` yêu cầu tính chất:

~~~text
Nếu R copy = new R(r.component1(), r.component2(), ...)
thì r.equals(copy) phải là true.
~~~

Khi một accessor tự clone array, mặc định equality theo reference có thể làm điều kiện này sai; vì vậy constructor/accessor/equality/hashCode cần được thiết kế **thống nhất**.

## 11. Các tình huống đặc biệt và lưu ý hiện hành

### 11.1. JSON binding, ORM và framework

Record class có canonical constructor và accessors `component()`, không phải JavaBeans setters. Một số thư viện hỗ trợ record chính thức và có thể gọi canonical constructor; các thư viện cũ/phiên bản cũ có thể không hỗ trợ hoặc tìm constructor không tham số.

Đừng mặc định mọi framework sẽ áp dụng `List.copyOf`/`validate` giống nhau nếu nó dùng reflection, serialization, hay bỏ qua constructor. **Kiểm tra đúng phiên bản framework và test serialization/deserialization thật** trước khi dựa vào đó.

Với **Java Object Serialization** khi record implements `Serializable`, Javadoc `java.lang.Record` nói deserialization của serializable records có cơ chế riêng và **canonical constructor được gọi**; một số special methods của ordinary serializable classes như `readObject/writeObject` bị bỏ qua với records. Đây là một lý do không nên áp dụng máy móc cùng một mẫu hook cho class và record.

### 11.2. Bất biến và concurrency

Khi mọi components đều là immutable values, record dễ chia sẻ giữa threads hơn vì trạng thái không đổi sau construction. Tuy nhiên:

- Nếu component trỏ tới mutable object, record vẫn có **shared mutable state**.
- Defensive copying tại boundary không tự tạo transaction hoặc locking cho nguồn đang bị thay đổi **đồng thời khi copy**.
- Cần snapshot từ một nguồn nhất quán hoặc giữ lock thích hợp nếu một thread khác có thể sửa collection **trong lúc copy**.
- Không dùng một record nhiều components làm thay thế cho concurrency control hoặc database transaction.

`List.copyOf` là snapshot theo API; nó không tự bảo đảm đọc atomic của một nguồn đang được sửa bất đồng bộ bởi threads khác.

### 11.3. Serialization và dữ liệu không tin cậy

Dù canonical constructor validate input, không nên đồng nhất record với sanitizer hoàn chỉnh. Tùy format/framework, dữ liệu mạng cần schema validation, limits, error handling và security review. Với Java native deserialization từ nguồn không tin cậy, **tránh sử dụng trực tiếp** hoặc áp dụng các chính sách lọc/giới hạn nghiêm ngặt. Record không tự biến một serialized byte stream lạ thành dữ liệu an toàn.

### 11.4. Defensive copying có chi phí

Clone một mảng dài hay copy một graph lớn mất CPU/bộ nhớ. Không loại bỏ phòng vệ chỉ vì một microbenchmark khi record là security boundary hoặc value object quan trọng. Thay vào đó:

- Chọn component types immutable ngay từ thiết kế.
- Snapshot một lần khi chuyển từ mutable DTO vào domain.
- Tránh sao chép lặp lại khi dữ liệu đã ở trong một immutable value abstraction phù hợp.
- Dùng representation khác khi phải xử lý những khối dữ liệu lớn (streaming, memory-mapped, content-addressed storage).
- Đo đúng workload và chú ý việc caller có cần truy xuất dữ liệu nhiều lần hay không.

## 12. Checklist code review

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Mục đích record | Đây là **value/snapshot**, hay thực chất là một entity cần mutable lifecycle? |
| Mốc Java | Target JDK ít nhất 16 (bài dùng Java 17+), không bật preview cũ? |
| Header | Mỗi component có type và semantics phù hợp? |
| Constructor | Có validate null/range/cross-field rules không? |
| Chuẩn hóa | Có normalize một cách có chủ đích và nhất quán không? |
| Collections | Có `List.copyOf`/`Map.copyOf` ở boundary không? |
| Elements | Mỗi element có thực sự immutable không? |
| Nested graph | Có list/map/array mutable ở sâu hơn không? |
| Arrays | Có clone trong constructor **và accessor** không? |
| Equality | Nếu component là array, có xử lý content equality/hash không? |
| Log | `toString` có vô tình làm lộ secrets không? |
| Numeric safety | Có dùng checked arithmetic tại các phép nhân/cộng có thể tràn? |
| Errors | Invalid input báo lỗi rõ, không bị nuốt silent? |
| Tests | Có mutate nguồn sau construction và mutate giá trị getter trả về? |
| Concurrency | Nguồn copy có ổn định trong lúc chụp snapshot? |
| Frameworks | Parser/ORM/serializer có thật sự gọi canonical constructor đúng cách không? |
| Schema | Có chính sách tiến hóa record components khi API hoặc format thay đổi? |

### Bộ test tối thiểu nên có

1. Tạo record với dữ liệu hợp lệ, assert components.
2. Gán input null, blank, range sai, collection null/element null; assert loại lỗi mong đợi.
3. Sửa `ArrayList`/`HashMap` ban đầu sau khi record được tạo; assert bản ghi không đổi.
4. Gọi `record.lines().add(...)` hoặc `record.tags().put(...)`; assert bị từ chối.
5. Với array, sửa array **đầu vào** và array lấy từ **accessor**; assert bytes bên trong không đổi.
6. So sánh hai record có cùng giá trị, assert equals/hashCode nhất quán.
7. Với mutable nested element, assert copy nông sẽ lộ mutation; sửa design để chuyển thành immutable value.
8. Kiểm tra tổng số lượng/giá tiền ở các biên tràn, không âm thầm cho phép overflow.
9. Kiểm tra biểu diễn trong logs không in dữ liệu nhạy cảm.
10. Kiểm tra framework/JSON/database adapter theo môi trường thực nếu ứng dụng sử dụng.

## 13. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| “Record tự immutable sâu” | Mutable component vẫn đổi được | Thiết kế immutable graph hoặc defensive copy |
| `record R(List<T> x) {}` với ArrayList đầu vào | Caller có thể sửa list sau khi tạo | `x = List.copyOf(x)` trong compact constructor |
| Chỉ `Collections.unmodifiableList(input)` | View vẫn thay đổi theo backing list | `List.copyOf(input)` khi cần snapshot |
| `List.copyOf` với các DTO mutable | Membership bất biến nhưng fields của element vẫn đổi | Convert từng DTO thành immutable value record |
| `Map.copyOf` với values là List mutable | Map không sửa được nhưng list value vẫn đổi | Deep-copy values trước khi đóng băng map |
| `List.copyOf` với null element | Ném `NullPointerException` | Validate/loại null theo domain trước khi copy |
| Đoán thứ tự duyệt `Map.copyOf` | Output có thể thay đổi | Dùng representation có order rõ |
| Coi `copyOf` luôn tạo instance mới | Dựa vào identity không được bảo đảm | Test nội dung snapshot, không test `!=` |
| Chỉ clone mảng khi constructor | Accessor vẫn lộ array thật | Clone ở cả hai chiều |
| Chỉ clone mảng ở accessor | Caller còn giữ input array | Clone ở constructor nữa |
| Giữ auto equals/hashCode cho array và mong content equality | Hai mảng khác identity dù cùng bytes | Override cả equals/hashCode hoặc đổi representation |
| Override equals mà quên hashCode | Vi phạm contract, lỗi HashMap/HashSet | Giữ equals/hashCode nhất quán |
| Gán `this.component = ...` trong compact constructor | Compile-time error | Gán lại parameter `component = ...` |
| Quên validate component | Record lưu được trạng thái nghiệp vụ không hợp lệ | Đặt invariants trong canonical constructor |
| Tính tiền bằng `double` không có quy tắc làm tròn | Dễ có lỗi biểu diễn thập phân | Dùng long đơn vị nhỏ nhất hoặc BigDecimal khi phù hợp |
| Cộng/nhân long không kiểm tra overflow | Kết quả có thể wrap | `Math.addExact`/`Math.multiplyExact` |
| In toàn bộ record vào log | Dữ liệu nhạy cảm có thể lộ | ToString có kiểm soát, logger allowlist |
| Tưởng `record` tự chạy không cần preview trên Java 14 | Java14 chỉ preview | Dùng Java16+; bài yêu cầu Java17 |
| Gán record cho ORM/serializer không hỗ trợ | Binding, hydration thất bại | Kiểm tra version và test adapter |
| Dùng `record` làm DB transaction/concurrency guard | Không có isolation/locking tự động | Áp dụng domain/transaction control riêng |

## 14. Bài tập và lời giải

**Câu 1.** Vì sao record sau chưa bất biến sâu?

~~~java
record Profile(List<String> roles) {}
~~~

**Đáp án:** `roles` là final reference nhưng có thể trỏ tới mutable list. Người gọi còn giữ list gốc có thể thêm/bớt roles, làm record quan sát thấy thay đổi.

**Câu 2.** Viết compact constructor để không chấp nhận danh sách rỗng/null và phòng vệ khi caller sửa `roles`.

~~~java
record Profile(List<String> roles) {
    Profile {
        roles = List.copyOf(roles);
        if (roles.isEmpty()) {
            throw new IllegalArgumentException("no roles");
        }
    }
}
~~~

`List.copyOf` từ chối null list/null element; record giữ unmodifiable membership snapshot.

**Câu 3.** `Collections.unmodifiableList(input)` và `List.copyOf(input)` có giống nhau không?

**Đáp án:** Không. Unmodifiable wrapper chỉ là **view** của input; sửa backing list vẫn thấy thay đổi qua view. `List.copyOf` giữ snapshot membership tại lúc tạo.

**Câu 4.** `record R(byte[] data) {}` có tự an toàn khi input array bị sửa không?

**Đáp án:** Không. Field final nhưng mảng mutable. Cần `data = data.clone();` trong constructor và override `data()` để trả clone.

**Câu 5.** Vì sao cần override `equals/hashCode` khi dùng byte[] component và muốn value equality?

**Đáp án:** Array mặc định có identity equality; generated record equals dựa trên component equality sẽ không so sánh từng byte. Override `Arrays.equals` và `Arrays.hashCode` theo cùng nội dung để giữ contract của record.

**Câu 6.** List đã được `List.copyOf`, nhưng element là `MutableLine`. Điều gì vẫn có thể thay đổi?

**Đáp án:** Properties của từng `MutableLine` còn sửa được qua các alias khác. `copyOf` không deep-copy elements. Chuyển thành immutable `FrozenLine` trước khi tạo frozen list.

**Câu 7.** Có được gán `this.lines = List.copyOf(lines);` trong compact constructor không?

**Đáp án:** Không. JLS cấm gán trực tiếp component fields trong compact constructor. Dùng `lines = List.copyOf(lines);` và để assignment ngầm xảy ra cuối constructor.

**Câu 8.** Khi `quantity` là `int` còn `priceCents` là `long`, vì sao dùng `Math.multiplyExact`?

**Đáp án:** Để phát hiện tích vượt `long` bằng `ArithmeticException` thay vì âm thầm overflow. Validation `quantity > 0` và `priceCents >= 0` vẫn phải tách riêng.

**Câu 9.** `Map.copyOf` có bảo đảm giữ thứ tự của `LinkedHashMap` đầu vào không?

**Đáp án:** Không. Map được trả là unmodifiable nhưng iteration order không được bảo đảm. Nếu thứ tự là hợp đồng dữ liệu, cần thiết kế representation có thứ tự riêng.

**Câu 10.** Khi nào phù hợp dùng record thay class mutable?

**Đáp án:** Khi cần transparent value/data carrier với components cố định, constructor có thể kiểm tra invariants và dùng immutable values. Với entity có identity/lifecycle mutations phức tạp, class/domain aggregate riêng có thể phù hợp hơn.

**Câu 11.** Nếu `Blob.bytes()` trả clone và equals vẫn do compiler tự tạo, có thể vi phạm invariant nào?

**Đáp án:** Javadoc record yêu cầu bản copy được tạo từ component accessors phải equals bản gốc. Nếu accessor trả mảng clone và auto equals so identity mảng, bản mới có thể không equals bản gốc. Dùng equality/hash theo byte contents.

**Câu 12.** `record Order(List<Line> lines)` có bảo đảm thread-safe nếu thread khác đồng thời sửa ArrayList lúc constructor gọi `List.copyOf`?

**Đáp án:** Không. `copyOf` không tự cung cấp atomic snapshot khi nguồn bị mutate bất đồng bộ. Cần phối hợp đồng bộ hoặc nhận một snapshot đã ổn định.

**Câu 13.** `List.copyOf` có phải sẽ luôn gọi `new ArrayList(...)` bên trong?

**Đáp án:** Không nên giả định triển khai cụ thể hay việc luôn cấp phát bản sao. JDK có thể tái sử dụng một unmodifiable list phù hợp. Hợp đồng quan trọng là unmodifiable membership snapshot.

**Câu 14.** Nếu record dùng để nhận API request, validation trong compact constructor có thay thế hoàn toàn kiểm tra authentication/schema không?

**Đáp án:** Không. Constructor giúp giữ domain invariant sau khi object được tạo; authentication, giới hạn size, parse/schema validation và security policy còn thuộc các boundary khác.

## 15. Tài liệu tham khảo chính thức

- [OpenJDK JEP 359 — Records](https://openjdk.org/jeps/359): lần giới thiệu `record` ở Java 14 dưới dạng preview.
- [OpenJDK JEP 384 — Records (Second Preview)](https://openjdk.org/jeps/384): giai đoạn preview tại Java 15.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): mốc trở thành tính năng chính thức tại Java 16.
- [Oracle Java 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): record header, generated members, canonical và compact constructors, validation.
- [Oracle Java 17 — java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): shallow immutability, canonical constructor, defensive copies và copy-equals invariant.
- [Oracle Java 25 — java.lang.Record](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): record semantics hiện hành, equality, hashCode và serialization note.
- [Java Language Specification 25 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): quy tắc record components, constructors và methods.
- [Java Language Specification 25 — `8.10.4.2 Compact Constructors](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2): gán tham số, cấm gán component fields trực tiếp trong compact constructor.
- [Oracle Java 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable membership snapshot, null rejection, hạn chế shallow copy.
- [Oracle Java 17 — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map snapshot, null rejection, unspecified iteration order.
- [Oracle Java 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): validation tham chiếu không null.
- [Oracle Java 17 — Arrays.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): value equality và content hash của primitive arrays.
- [Oracle Java 17 — Math.addExact/multiplyExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): các phép toán kiểm tra tràn cho kiểu nguyên.
- [Oracle Java 25 — Serialization of Records](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/serial-arch.html): serial form và sự khác nhau của record với Serializable class thông thường.

**Ghi nhớ:** `record` đem lại **final component references và cơ chế value object thuận tiện**, chứ không tự tạo **deep immutability**. Hãy validate và chuẩn hóa trong **canonical/compact constructor**, chụp snapshot collections bằng `List.copyOf`/`Map.copyOf`, chuyển các phần tử mutable thành immutable values, và clone array **cả khi nhận và khi trả**. Nếu record chứa array và cần content equality, phải thiết kế `equals`/`hashCode` nhất quán. Một record có invariants rõ, không có mutable aliases ngoài ý muốn và được kiểm thử ở các ranh giới dữ liệu sẽ đáng tin cậy hơn nhiều so với chỉ thay `class` bằng từ khóa `record`.