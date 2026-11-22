# Record pattern và tính bất biến của record (Java 21)

## Mục tiêu

Sau bài này, bạn có thể phân biệt **record class** với **record pattern**, giải thích vì sao record chỉ **bất biến ở mức nông (shallow immutability)**, nhận ra lúc một phép tách record làm lộ tham chiếu có thể thay đổi, và thiết kế record giữ được bất biến mong muốn khi chứa `List`, mảng hoặc các đối tượng có trạng thái.

**Phiên bản:** `record` là tính năng chính thức từ Java 16; **record patterns** và pattern matching cho `switch` là tính năng chính thức trong **Java 21** (không cần `--enable-preview`). Các ví dụ chạy với JDK 21 trở lên.

## 1. Record class và record pattern khác nhau thế nào?

Một `record` khai báo kiểu dữ liệu có tập component cố định:

```java
record Point(int x, int y) {}
```

Trình biên dịch cung cấp các trường thành phần `private final`, accessor `x()` và `y()`, constructor chuẩn (canonical constructor), cùng `equals(Object)`, `hashCode()`, `toString()` dựa trên các component. Ví dụ:

```java
Point p = new Point(2, 4);
System.out.println(p.x()); // 2
System.out.println(p);     // Point[x=2, y=4]
```

Trái lại, **record pattern** là mẫu để *kiểm tra kiểu và tách component* của một giá trị record. Ví dụ, khi `value` có kiểu khai báo `Object`:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

`Point(int x, int y)` trong điều kiện trên **không phải lời gọi constructor**. Nó kiểm tra `value` có khớp record `Point` hay không, sau đó lấy hai component và gán vào biến pattern `x`, `y` để dùng trong nhánh thành công. Viết `Point(var x, var y)` cũng được: Java suy luận kiểu của hai biến là `int`.

So sánh ba cách truy cập dữ liệu:

| Cách | Ý nghĩa |
| --- | --- |
| `p.x()` | Lấy component qua accessor |
| `value instanceof Point p` | Kiểm tra kiểu, giữ tham chiếu đến toàn bộ `Point` |
| `value instanceof Point(var x, var y)` | Kiểm tra kiểu rồi tách trực tiếp hai component |

**Quan hệ cốt lõi:** record class quyết định cách lưu và công bố dữ liệu; record pattern quyết định cách **đọc/tách** dữ liệu đó trong một biểu thức match. Pattern **không tạo bản sao record**, **không đổi trạng thái record** và **không tự làm dữ liệu an toàn hơn**.

## 2. Record pattern hoạt động như thế nào?

Cấu trúc tổng quát:

```java
RecordType(pattern1, pattern2, ...)
```

- `RecordType` phải là kiểu record phù hợp với giá trị được kiểm tra.
- Số pattern thành phần phải tương ứng số component, đúng thứ tự trong khai báo record.
- Mỗi component được lấy bằng accessor của record rồi được so khớp với pattern tương ứng.
- Các biến pattern chỉ dùng được tại những vị trí mà trình biên dịch xác định phép match đã thành công.

Ví dụ với record lồng nhau:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}

Object shape = new Rectangle(new Point(1, 2), new Point(5, 8));

if (shape instanceof Rectangle(
        Point(int left, int top),
        Point(int right, int bottom))) {
    System.out.println(left + "," + top + " -> " + right + "," + bottom);
}
// In: 1,2 -> 5,8
```

`Rectangle(Point(...), Point(...))` là **nested record pattern**: Java đối chiếu `Rectangle` rồi tiếp tục tách từng `Point`. Cách này tránh ép kiểu thủ công và các chuỗi gọi accessor dài. Khi muốn giữ cả đối tượng con, có thể dùng `var`, ví dụ `Rectangle(Point(var x, var y), var otherCorner)`.

### `null` và các điều kiện match

`null` **không khớp với bất kỳ record pattern nào**. Do đó:

- `value instanceof Point(var x, var y)` trả `false` nếu `value == null`.
- Với `record Holder(Point point) {}`, giá trị `new Holder(null)` có thể khớp `Holder(var point)`, nhưng **không** khớp `Holder(Point(var x, var y))`, vì component `point` là `null`.
- Trong `switch` có pattern, dùng `case null` để xử lý `null`; nếu thiếu nhánh phù hợp cho `null`, `switch` có thể ném `NullPointerException`. `default` đơn lẻ không thay thế việc xử lý `null`.

Record pattern cũng có mặt trong `switch` của Java 21. Nhánh có `when` cho phép đặt điều kiện bổ sung; đặt nhánh cụ thể trước nhánh tổng quát để tránh bị che khuất (dominated).

## 3. Tính bất biến của record: `final` không đồng nghĩa với bất biến sâu

Mỗi component được lưu trong một trường `final`, nên không thể gán lại trường sau khi đối tượng đã được khởi tạo. Ví dụ `Point` không có setter cho `x`/`y`; nếu muốn tọa độ khác, thường tạo một `Point` mới.

Nhưng `final` **khóa tham chiếu ở trường**, không đóng băng đối tượng mà tham chiếu đó trỏ đến. Xét:

```java
record Profile(String name, List<String> roles) {}

List<String> source = new ArrayList<>(List.of("read"));
Profile profile = new Profile("An", source);

// Bản thân trường roles không thể được gán sang List khác,
// nhưng List đang được trỏ tới vẫn có thể đổi:
source.add("write");
System.out.println(profile.roles()); // [read, write]
```

Record vừa tạo giữ **cùng tham chiếu** `source`. Nếu ai đó thay đổi `source`, dữ liệu nhìn thấy qua `profile.roles()` cũng thay đổi. Tương tự:

```java
if (profile instanceof Profile(var name, var roles)) {
    roles.add("admin"); // thay đổi List mà component đang tham chiếu
}
```

Record pattern chỉ trích xuất tham chiếu `roles`; phép tách không clone `List`. Vì thế, **record được bảo đảm bất biến về các trường component, nhưng mặc định chỉ shallowly immutable**, không bảo đảm mọi object bên trong đều bất biến. Điều này cũng ảnh hưởng đến tính nhất quán khi chia sẻ dữ liệu giữa các luồng và khi dùng record có component mutable làm khóa của `HashMap`.

### Khi nào có thể xem record là bất biến theo nghĩa thực hành?

Một record chỉ chứa giá trị primitive, `String` hoặc các đối tượng bất biến đúng nghĩa thường phù hợp làm value object:

```java
record Coordinate(int latitude, int longitude) {}
record PersonName(String first, String last) {}
```

Với component kiểu `List`, mảng hoặc đối tượng mutable, cần chủ động bảo vệ lúc **nhận dữ liệu vào** và khi **trả dữ liệu ra**. Record lồng record cũng chỉ an toàn nếu các component sâu bên trong được kiểm soát tương tự.

## 4. Chương trình hoàn chỉnh: tách record và kiểm tra bất biến

Tạo tệp **`RecordPatternDemo.java`**:

```java
import java.util.*;

public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Rectangle(Point upperLeft, Point lowerRight) {}

    // Chỉ bất biến nông: List vẫn có thể thay đổi.
    record Profile(String name, List<String> roles) {}

    // Sao chép List khi tạo record để bảo vệ dữ liệu đầu vào.
    record SafeProfile(String name, List<String> roles) {
        SafeProfile {
            Objects.requireNonNull(name);
            roles = List.copyOf(roles);
        }
    }

    // Mảng cần sao chép cả khi nhận vào và khi trả ra.
    record Packet(byte[] data) {
        Packet {
            Objects.requireNonNull(data);
            data = data.clone();
        }

        @Override
        public byte[] data() {
            return data.clone();
        }

        // Mảng dùng equals/hashCode theo nội dung thay vì tham chiếu.
        @Override
        public boolean equals(Object other) {
            return other instanceof Packet p && Arrays.equals(data, p.data);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(data);
        }
    }

    static String inspect(Object value) {
        return switch (value) {
            case Rectangle(Point(var x1, var y1), Point(var x2, var y2)) ->
                    "Rectangle (" + x1 + "," + y1 + ") -> ("
                            + x2 + "," + y2 + ")";
            case Point(var x, var y) when x == y -> "Point on x=y: " + x;
            case Point(var x, var y) -> "Point (" + x + "," + y + ")";
            case null -> "null";
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(
                new Rectangle(new Point(1, 2), new Point(5, 8))));
        System.out.println(inspect(new Point(3, 3)));
        System.out.println(inspect(null));

        List<String> source = new ArrayList<>(List.of("read"));
        Profile profile = new Profile("An", source);
        if (profile instanceof Profile(var name, var roles)) {
            roles.add("write");
        }
        System.out.println(profile.roles());

        SafeProfile stable = new SafeProfile("An", source);
        source.add("delete");
        System.out.println(stable.roles());

        try {
            stable.roles().add("admin");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }

        byte[] buffer = {1, 2};
        Packet packet = new Packet(buffer);
        buffer[0] = 9;
        if (packet instanceof Packet(var snapshot)) {
            snapshot[1] = 8;
        }
        System.out.println(Arrays.toString(packet.data()));
        System.out.println(packet.equals(new Packet(packet.data())));
    }
}
```

Biên dịch và chạy trên JDK 21 trở lên:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Kết quả:

```text
Rectangle (1,2) -> (5,8)
Point on x=y: 3
null
[read, write]
[read, write]
unmodifiable
[1, 2]
true
```

Giải thích những điểm đáng chú ý:

1. `inspect` dùng nested record patterns để đọc hai điểm của `Rectangle`. Với `Point(3,3)`, nhánh `when x == y` được chọn trước nhánh `Point` chung.
2. `Profile` dùng chung `source` với bên ngoài. Biến `roles` được tách bằng pattern cũng trỏ tới danh sách đó, nên thêm `"write"` làm thay đổi dữ liệu thấy từ `profile`.
3. `SafeProfile` gọi `List.copyOf(roles)` trong **compact canonical constructor**. Vì vậy thay đổi tiếp ở `source` không ảnh hưởng `stable`; danh sách trả về cũng từ chối `add`.
4. `Packet` clone mảng ở constructor và accessor. Khi pattern `Packet(var snapshot)` được so khớp, accessor `data()` được dùng, nên `snapshot` là một bản sao. Việc sửa `buffer` hoặc `snapshot` không làm đổi component thật bên trong.
5. `Packet` tự định nghĩa `equals` và `hashCode` bằng `Arrays.equals`/`Arrays.hashCode`. Nếu giữ cài đặt sinh tự động, component là mảng sẽ được so bằng danh tính tham chiếu, không phải nội dung các phần tử. Hai `Packet` có byte giống nhau nhưng mảng khác nhau sẽ bị xem là không bằng nhau; đồng thời một accessor trả bản sao có thể vi phạm quy tắc sao chép của record. Vì vậy phải xem cả **bất biến dữ liệu** lẫn **ngữ nghĩa equality**.

## 5. Thiết kế record an toàn với dữ liệu mutable

**Bước 1: Kiểm tra invariant trong constructor.** Compact canonical constructor cho phép kiểm tra và chuẩn hóa tham số trước khi trình biên dịch tự gán vào trường:

```java
record Money(String currency, long cents) {
    Money {
        Objects.requireNonNull(currency, "currency");
        if (currency.isBlank()) {
            throw new IllegalArgumentException("currency must not be blank");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be >= 0");
        }
    }
}
```

Chỉ dùng constructor để thiết lập/kiểm soát component; không dùng record cho mô hình cần thay đổi định danh hoặc trạng thái nội tại liên tục.

**Bước 2: Cắt alias từ đầu vào.** Với `List<String>`, `List.copyOf` thường là lựa chọn phù hợp: nó tạo/dùng một danh sách không sửa được, tách khỏi các thay đổi sau này của danh sách đầu vào mutable, và không chấp nhận phần tử `null`. Với `Map`/`Set` có các phương thức `Map.copyOf` và `Set.copyOf` tương tự.

**Bước 3: Đánh giá độ sâu của component.** `List.copyOf` là bản sao **nông của các phần tử**. Nếu `List` chứa `StringBuilder` hoặc bean có setter, người giữ tham chiếu đến các phần tử đó vẫn có thể sửa nội dung dù danh sách không cho thêm/xóa. Ví dụ minh họa:

```java
record Notes(List<StringBuilder> items) {
    Notes {
        items = List.copyOf(items);
    }
}

// List không cho thêm/xóa, nhưng StringBuilder bên trong vẫn mutable.
StringBuilder text = new StringBuilder("A");
Notes notes = new Notes(List.of(text));
text.append("B");
System.out.println(notes.items().get(0)); // AB
```

Để bất biến sâu hơn, chuyển phần tử thành kiểu bất biến (chẳng hạn `String` hoặc một record chỉ chứa giá trị bất biến), hoặc sao chép từng phần tử với chính sách riêng của miền nghiệp vụ. Ví dụ `record Order(List<LineItem> items)` có `List.copyOf(items)` sẽ an toàn hơn nếu `LineItem` là record bất biến có component bất biến.

**Bước 4: Bảo vệ cả accessor với mảng/đối tượng mutable.** Chỉ clone đầu vào chưa đủ: nếu accessor trả thẳng mảng nội bộ thì bên ngoài vẫn sửa mảng đó được. Ngược lại, accessor clone nhưng không xem lại `equals`/`hashCode` có thể khiến record không còn hành xử như một value object đúng nghĩa.

**Bước 5: Giữ contract của record.** Về mặt giá trị, một bản sao được dựng từ chính các accessor nên bằng bản gốc:

```java
R copy = new R(r.component1(), r.component2());
assert r.equals(copy);
```

Đây là **mẫu diễn giải** cho record `R` có hai component, không phải một đoạn Java chạy độc lập. Khi tùy biến constructor, accessor, `equals` hay `hashCode`, phải bảo toàn contract tương ứng. Đặc biệt tránh accessor có side effect: record pattern sử dụng accessor để tách thành phần, nên side effect sẽ làm phép match khó đoán.

## 6. Record pattern không thay đổi đặc tính bất biến của record

Hãy tách rõ ba lớp hành vi:

| Lớp | Điều gì được bảo đảm? | Điều gì không được bảo đảm? |
| --- | --- | --- |
| Trường của record | Tham chiếu/giá trị component không được gán lại sau khởi tạo | Đối tượng được tham chiếu tự động bất biến |
| Record pattern | Kiểm tra kiểu và lấy component qua accessor | Không clone, không khóa, không validate lại dữ liệu |
| Defensive copy + component bất biến | Có thể chặn alias mutable và giữ invariant dữ liệu | `List.copyOf` tự động sao chép sâu các phần tử mutable |

Từ đó suy ra: nếu record chứa `List` mutable, `case Profile(var name, var roles)` làm lộ cùng tham chiếu mà `profile.roles()` có thể trả về. Nếu record được thiết kế có copy và accessor an toàn, pattern cũng quan sát qua accessor đó; **tính an toàn đến từ thiết kế record**, không đến từ cú pháp pattern.

Record pattern phù hợp để đọc mô hình dữ liệu lồng nhau, xử lý các trường hợp trong `switch` và viết các phép phân tích dữ liệu rõ ràng. Khi dữ liệu cần thay đổi thường xuyên, hãy cân nhắc một lớp mutable có kiểm soát hoặc tạo **record mới** để biểu diễn trạng thái mới:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}
Counter before = new Counter(1);
Counter after = before.increment(); // before.value() vẫn bằng 1
```

### Lỗi thường gặp

- **Dùng record với `List`/array rồi mặc định nó bất biến sâu:** thêm defensive copy, chọn component bất biến và bảo vệ accessor khi cần.
- **Nghĩ `var roles` trong record pattern là bản sao:** đó là biến nhận giá trị component; với kiểu tham chiếu, nó có thể trỏ tới cùng object mutable.
- **Đặt `case Point(var x, var y)` trước `case Point(var x, var y) when ...`:** nhánh tổng quát có thể che nhánh cụ thể; đảo thứ tự.
- **Cho rằng nested pattern nhận cả `null`:** record pattern không match `null`, kể cả `null` ở component lồng.
- **Dùng `record Payload(byte[] bytes)` rồi dựa vào `equals` tự động để so nội dung mảng:** mảng mặc định so tham chiếu; phải chọn chính sách so sánh phù hợp.
- **Viết ví dụ record pattern trên JDK 17 mà không kiểm tra phiên bản:** JDK 17 hỗ trợ record, nhưng record pattern chỉ chính thức ở Java 21.
- **Dùng `record` thay cho mọi class:** record phù hợp nhất khi hình dạng dữ liệu là hợp đồng công khai, ổn định; record không hỗ trợ kế thừa từ class tùy ý hay thêm trường instance nằm ngoài component.

## 7. Tự kiểm tra

1. Vì sao `record Profile(List<String> roles)` vẫn có thể thay đổi nội dung quan sát được sau khi constructor chạy? **Vì trường `final` giữ cố định tham chiếu, còn đối tượng `List` có thể bị sửa.**
2. `if (o instanceof Point(int x, int y))` có tạo `Point` mới không? **Không.** Nó match kiểu và lấy component của đối tượng sẵn có.
3. Nếu `List.copyOf` chứa một đối tượng mutable, record đã bất biến sâu chưa? **Chưa.** Cần bảo vệ phần tử.
4. `Holder(Point(var x, var y))` có khớp với `new Holder(null)` không? **Không.** Nested `Point` không match `null`.
5. Vì sao clone mảng trong cả constructor lẫn accessor còn cần cân nhắc equality? **Vì `equals` sinh sẵn so tham chiếu mảng; giá trị sao chép có nội dung giống nhau có thể không được xem là bằng nhau.**

## Tham khảo

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Java SE 21 API — java.lang.Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html)
