# NullPointerException khi thiếu `case null` trong `switch` (Java 21+)

## 1. Vấn đề cốt lõi

Với `switch` nhận giá trị tham chiếu (**reference type**), nếu biểu thức selector được đánh giá thành `null` mà switch **không có nhãn `case null`**, Java ném **`NullPointerException` (NPE)**. Điều này đúng cả khi trong switch có nhánh `default`:

~~~java
Object value = null;

String result = switch (value) {
    case String s -> "String: " + s;
    default -> "Giá trị khác";
};
// Runtime: NullPointerException, KHÔNG trả "Giá trị khác".
~~~

Lỗi hay gặp là nghĩ rằng `default` tương đương `else` và sẽ nhận mọi thứ, kể cả `null`. **Không đúng.** `default` xử lý các giá trị không khớp nhãn khác theo quy tắc switch, nhưng `null` có quy tắc riêng: nếu thiếu `case null`, quá trình xử lý selector null ném NPE.

Cách sửa thông dụng trong Java 21:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String s -> "String: " + s;
        default -> "Giá trị khác";
    };
}

System.out.println(classify(null));  // Không có dữ liệu
System.out.println(classify(42));    // Giá trị khác
~~~

Bài này giải thích khi nào NPE xuất hiện, vì sao `default`/record pattern/total pattern không tự xử lý null, cách dùng `case null` hoặc chủ động từ chối null và cách kiểm tra lỗi bằng Java 21+.

**Phiên bản:** cú pháp pattern matching cho `switch` và nhãn `case null` được chuẩn hóa trong **Java 21 (JEP 441)**. Những phiên bản trước đã có các giai đoạn preview; để biên dịch các ví dụ ở đây không bật preview, dùng **JDK 21 trở lên**.

## 2. `selector` là gì, và NPE xảy ra khi nào?

Trong:

~~~java
String label = switch (value) {
    case String text -> "String: " + text;
    default -> "Other";
};
~~~

`value` là **selector expression**: biểu thức được đánh giá để chọn một nhánh `case`. Nếu giá trị của selector là `null` và switch không có `case null`, kết quả là NPE theo quy tắc của ngôn ngữ, **không phải** do đã chạy `text.toString()` hoặc do `default` tự ném lỗi.

Phân biệt:

1. **NPE do thiếu `case null`:** selector là `null`; switch không xử lý null; NPE xảy ra trong cơ chế lựa chọn nhánh.
2. **NPE do code bên trong nhánh:** selector có thể không null, nhánh đã khớp, nhưng code trong nhánh gọi phương thức trên một tham chiếu null. Có `case null` cho selector **không bảo đảm** mọi biến/field/component khác đều non-null.
3. **NPE do biểu thức selector tự gây ra trước khi trả giá trị:** ví dụ `switch (order.getStatus())` khi `order == null`; lúc này lời gọi `getStatus()` đã ném NPE, nên `case null` không thể “cứu” lỗi đó.

Ví dụ loại (3):

~~~java
// Khi order là null, gọi order.status() sẽ NPE trước khi switch có selector.
String result = switch (order.status()) {
    case null -> "Không có trạng thái";
    default -> "Có trạng thái";
};
~~~

Để xử lý an toàn, kiểm tra `order` **trước khi truy cập**; hoặc tạo selector mà chính bản thân nó được phép là `null`:

~~~java
String status = order == null ? null : order.status();

String result = switch (status) {
    case null -> "Không có trạng thái";
    default -> "Có trạng thái";
};
~~~

Đây là các đoạn minh họa giả định đã có biến `order` và phương thức `status()`; chúng **không phải chương trình độc lập**.

## 3. Vì sao `default` không bắt được `null`?

Xét:

~~~java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

- `unsafe("Java")`: selector là `String` không null, vào `case String s`.
- `unsafe(10)`: selector là `Integer` không null, không khớp `String`, vào `default`.
- `unsafe(null)`: selector null, **NPE**, không vào `default`.

Sửa bằng cách biểu diễn rõ chính sách đối với null:

~~~java
static String safe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

Điểm cần nhớ: việc có `default` giúp bao phủ các **kiểu/giá trị thông thường còn lại** và hỗ trợ yêu cầu *exhaustiveness*, nhưng không ngầm biến selector null thành một giá trị mặc định.

Điều này áp dụng cho **cả switch expression và switch statement**. Khác biệt giữa hai dạng là switch expression phải tạo ra giá trị, còn switch statement chủ yếu điều khiển thực thi; quy tắc xử lý selector null vẫn giống nhau.

## 4. `case null`: ba cách thiết kế chính sách

### 4.1. Trả về một giá trị hợp lệ cho null

Dùng khi null có ý nghĩa nghiệp vụ, ví dụ “chưa có dữ liệu”:

~~~java
static String display(Object value) {
    return switch (value) {
        case null -> "Chưa có dữ liệu";
        case String s -> s;
        default -> "Không phải chuỗi";
    };
}
~~~

Ưu điểm: code rõ ràng, không cần một vòng `if (value == null)` bên ngoài switch; null trở thành trường hợp được khai báo ngay cạnh các case khác.

### 4.2. Chủ động từ chối null bằng exception có ý nghĩa

Không phải lúc nào null cũng là dữ liệu hợp lệ. Nếu hợp đồng API cấm null, có thể ném exception rõ ràng:

~~~java
static String displayStrict(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value không được null");
        case String s -> "String: " + s;
        default -> "Khác";
    };
}
~~~

Cách này **không** “sửa” giá trị null; nó chuyển từ NPE ngầm khó hiểu sang việc từ chối có chủ đích. Chọn `IllegalArgumentException` hoặc exception domain phù hợp với hợp đồng của API. Một lựa chọn khác là kiểm tra trước:

~~~java
Objects.requireNonNull(value, "value không được null");
return switch (value) {
    case String s -> s;
    default -> "Khác";
};
~~~

`Objects.requireNonNull` vẫn ném **NPE**, nhưng thông điệp chỉ rõ tiền điều kiện bị vi phạm. Đây có thể là lựa chọn hợp lý nếu API quy ước null là lỗi lập trình, không phải một trạng thái nghiệp vụ có thể phục hồi.

### 4.3. Gom `case null, default`

Java 21 cho phép kết hợp nhãn `null` với `default` nếu muốn chúng có **cùng hành vi**:

~~~java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "String: " + s;
        case null, default -> "Null hoặc kiểu khác";
    };
}
~~~

Cách này phù hợp khi không cần phân biệt null với các giá trị không mong đợi. Nhưng nếu null và dữ liệu không hỗ trợ mang ý nghĩa khác nhau, hai nhánh tách biệt sẽ dễ theo dõi log và metric hơn.

**Giới hạn cú pháp:** Java 21 không cho trộn `null` với một **pattern label** thông thường trong cùng danh sách như `case null, String s -> ...`. Đoạn này là lỗi biên dịch `invalid case label combination`. Chỉ kết hợp `null` với `default` theo dạng được phép ở trên, hoặc viết các nhánh riêng.

## 5. Pattern `case Object obj` vẫn không bắt null

Một lỗi dễ mắc khi thấy pattern có kiểu rất rộng là:

~~~java
static String catchEverything(Object value) {
    return switch (value) {
        case Object obj -> "Đã nhận object";
    };
}
~~~

Switch trên là một dạng **exhaustive switch** với pattern `Object` dành cho những instance không null: compiler có thể coi toàn bộ các giá trị non-null được bao phủ.

Tuy nhiên:

~~~java
catchEverything(null); // Vẫn ném NullPointerException.
~~~

Lý do: `null` không khớp type pattern `Object obj`. Đối với switch selector null, luật ngôn ngữ đòi hỏi `case null` riêng. Không có ngoại lệ chỉ vì pattern là `Object` hay một kiểu cha chung.

Để nhận null thành một kết quả bình thường:

~~~java
static String catchEverythingIncludingNull(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case Object obj -> "Object: " + obj.getClass().getSimpleName();
    };
}
~~~

Trong nhánh `Object obj`, `obj` có thể được xem là non-null, vì null đã được xử lý riêng và type pattern không khớp null.

## 6. Exhaustiveness của sealed hierarchy không phải null-safety

Sealed interface cho phép mô tả tập subtype khép kín:

~~~java
sealed interface Message permits TextMessage, CountMessage {}

record TextMessage(String text) implements Message {}
record CountMessage(int count) implements Message {}
~~~

Với switch trên `Message`:

~~~java
static String describe(Message message) {
    return switch (message) {
        case TextMessage(var text) -> "Tin: " + text;
        case CountMessage(var count) -> "Đếm: " + count;
    };
}
~~~

Đây là switch expression **exhaustive tại compile time** đối với các subtype hợp lệ của `Message`: không cần `default`. Nhưng:

~~~java
describe(new CountMessage(3)); // "Đếm: 3"
describe(null);                // NullPointerException.
~~~

Câu “switch đã exhaustive” chỉ nói về độ bao phủ theo luật kiểm tra kiểu; nó **không** nói rằng switch tự nhận null. Để xử lý null có chủ đích:

~~~java
static String describeSafe(Message message) {
    return switch (message) {
        case null -> "Thiếu thông điệp";
        case TextMessage(var text) -> "Tin: " + text;
        case CountMessage(var count) -> "Đếm: " + count;
    };
}
~~~

Khi gặp NPE trong một switch đầy đủ các subtype, đừng vội bổ sung `default` và nghĩ đã sửa. Hãy điều tra **selector có thể null từ đâu**, sau đó quyết định trả giá trị, ném lỗi hợp đồng rõ ràng hoặc ngăn null từ ranh giới dữ liệu.

## 7. Record pattern: selector null khác component null

Trong một chương trình pattern matching, có hai vị trí null thường bị nhầm lẫn.

**Trường hợp A — selector của switch là null.**

~~~java
Object input = null;

String label = switch (input) {
    case null -> "NULL";
    case Shipment(var id, var destination) -> id;
    default -> "Khác";
};
~~~

Nếu **bỏ `case null`**, selector null gây NPE. Record pattern `Shipment(...)` sẽ **không** được chọn thay cho null.

**Trường hợp B — record selector không null, nhưng một component là null.**

~~~java
record Address(String city) {}
record Shipment(String id, Address destination) {}

Object input = new Shipment("S-2", null);

String label = switch (input) {
    case Shipment(var id, Address(var city)) ->
        id + " đến " + city;
    case Shipment(var id, var destination) ->
        id + " thiếu địa chỉ";
    case null -> "NULL";
    default -> "Khác";
};
System.out.println(label); // S-2 thiếu địa chỉ
~~~

Ở trường hợp B:

1. Selector là một instance `Shipment`, nên bản thân nó **không null**.
2. Nested record pattern `Address(var city)` **không khớp** với component `destination == null`.
3. Switch thử tiếp nhánh `Shipment(var id, var destination)`: `var destination` là component pattern không điều kiện đối với kiểu `Address` được khai báo và có thể ràng buộc giá trị null.
4. Nhánh này trả thông điệp thiếu địa chỉ. Không có NPE do thiếu `case null` của selector.

**Trường hợp C — record trong tồn tại nhưng field tham chiếu bên trong là null.**

~~~java
Object input = new Shipment("S-3", new Address(null));

String label = switch (input) {
    case Shipment(var id, Address(var city)) ->
        id + " đến " + (city == null ? "không rõ" : city);
    case Shipment(var id, var destination) ->
        id + " thiếu địa chỉ";
    case null -> "NULL";
    default -> "Khác";
};
System.out.println(label); // S-3 đến không rõ
~~~

Record pattern `Address(var city)` khớp vì đối tượng `Address` tồn tại. Biến `city` có thể nhận null; chính code nhánh phải tự quyết định xử lý null thế nào trước khi gọi `city.length()` hay `city.toUpperCase()`.

**Tóm lại:** `case null` xử lý **selector** null, không phải một “mạng an toàn” cho **mọi component** của một record. Cần đánh giá riêng từng nơi dữ liệu có thể null.

## 8. `instanceof` và `switch` khác nhau khi gặp null

Hai biểu thức tưởng tương tự nhưng có quy tắc null khác nhau:

~~~java
Object value = null;

boolean matched = value instanceof String text;
System.out.println(matched); // false
~~~

`instanceof String text` trả **false** khi `value == null`; không ném NPE chỉ vì kiểm tra kiểu. Record pattern trong `instanceof` cũng không khớp selector null:

~~~java
boolean matchedRecord = value instanceof Shipment(var id, var destination);
// false, không phải NullPointerException do giá trị đầu vào null.
~~~

Ngược lại:

~~~java
String result = switch (value) {
    case String s -> s.toUpperCase();
    default -> "Khác";
};
// NPE do switch selector null.
~~~

Vì vậy không thể suy luận “`instanceof` null an toàn” thành “pattern switch không cần `case null`”. Null-safety phải được xét theo **cấu trúc ngôn ngữ đang dùng**.

## 9. `when` guard và thứ tự nhánh không giải quyết thiếu null case

Một guard chỉ chạy sau khi case pattern đã khớp:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "Chuỗi trắng";
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

- Với null, vào `case null`; guard `s.isBlank()` **không chạy**.
- Với `"   "`, case `String` đầu khớp và guard đúng, trả `"Chuỗi trắng"`.
- Với `"Java"`, guard sai, rơi sang case `String` thứ hai.
- Với một kiểu không phải `String`, vào `default`.

Nếu bỏ `case null`, guard kiểu `when s == null` hay `when value == null` **không** khiến null trở thành một String pattern match. NPE do selector null vẫn xảy ra. Hãy giải quyết null tại nhãn `case null` hoặc ở bước kiểm tra trước switch.

Về thứ tự: đặt pattern `case String s when s.isBlank()` **trước** `case String s` không guard; đặt case tổng quát trước có thể làm case có guard phía sau bị báo dominance, tức lỗi compile time khác với NPE runtime.

## 10. Switch truyền thống với `String`, enum và boxed number

Không chỉ pattern switch mới có rủi ro này.

### 10.1. Selector là `String`

~~~java
String status = null;

switch (status) {
    case "OPEN" -> System.out.println("Đang mở");
    default -> System.out.println("Không xác định");
}
// Thiếu case null, runtime: NullPointerException.
~~~

Sửa khi có thể dùng Java 21+:

~~~java
switch (status) {
    case null -> System.out.println("Thiếu trạng thái");
    case "OPEN" -> System.out.println("Đang mở");
    default -> System.out.println("Không xác định");
}
~~~

### 10.2. Selector là enum

~~~java
enum Mode { ON, OFF }

static String name(Mode mode) {
    return switch (mode) {
        case ON -> "BẬT";
        case OFF -> "TẮT";
    };
}
~~~

Dù các enum constants đã được xử lý đầy đủ, gọi `name(null)` vẫn ném NPE nếu không có `case null`.

### 10.3. Selector là primitive hay boxed reference?

Một selector có kiểu nguyên thủy `int` không thể nhận giá trị null; với switch trên `int` thuần, không có trường hợp selector null. Nhưng một selector kiểu **`Integer`** (wrapper/reference) **có thể** null:

~~~java
Integer number = null;

String label = switch (number) {
    case null -> "Không có số";
    case 0 -> "Zero";
    default -> "Khác";
};
~~~

Ở đây `case null` cho phép xử lý wrapper null. Nếu code thực hiện **unboxing** `number` trước khi vào switch (chẳng hạn tính `number.intValue()`), NPE có thể xảy ra ngay tại phép unboxing đó, trước khi case của switch có thể xử lý.

## 11. Ví dụ Java 21+ hoàn chỉnh và kết quả

Lưu thành **`NullSwitchDemo.java`**:

~~~java
public class NullSwitchDemo {
    record Address(String city) {}
    record Shipment(String id, Address destination) {}

    sealed interface Message permits TextMessage, CountMessage {}
    record TextMessage(String text) implements Message {}
    record CountMessage(int count) implements Message {}

    enum Mode { ON, OFF }

    static String withoutNullCase(Object value) {
        return switch (value) {
            case String s -> "Text: " + s;
            default -> "Khác";
        };
    }

    static String withNullCase(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Chuỗi trắng";
            case String s -> "Text: " + s;
            case Integer n -> "Số: " + n;
            case Shipment(var id, Address(var city)) ->
                    id + " đến " + (city == null ? "không rõ" : city);
            case Shipment(var id, var destination) ->
                    id + " thiếu địa chỉ";
            default -> "Kiểu khác";
        };
    }

    static String nullAndDefault(Object value) {
        return switch (value) {
            case String s -> "String: " + s;
            case null, default -> "Null hoặc kiểu khác";
        };
    }

    static String catchAllObject(Object value) {
        return switch (value) {
            case Object obj -> "Object: " + obj.getClass().getSimpleName();
        };
    }

    static String fromSealed(Message value) {
        return switch (value) {
            case TextMessage(var text) -> "Tin: " + text;
            case CountMessage(var count) -> "Đếm: " + count;
        };
    }

    static String modeNoNull(Mode value) {
        return switch (value) {
            case ON -> "BẬT";
            case OFF -> "TẮT";
        };
    }

    static String rejectNull(Object value) {
        return switch (value) {
            case null -> throw new IllegalArgumentException(
                    "value không được null");
            case String s -> "String: " + s;
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(withNullCase(null));
        System.out.println(withNullCase("   "));
        System.out.println(withNullCase("Java"));
        System.out.println(withNullCase(42));
        System.out.println(withNullCase(
                new Shipment("S-1", new Address("Hà Nội"))));
        System.out.println(withNullCase(new Shipment("S-2", null)));
        System.out.println(withNullCase(
                new Shipment("S-3", new Address(null))));
        System.out.println(withNullCase(2.5));
        System.out.println(nullAndDefault(null));
        System.out.println(nullAndDefault(7));
        System.out.println(fromSealed(new CountMessage(3)));

        try {
            withoutNullCase(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: thiếu case null");
        }

        try {
            catchAllObject(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: Object pattern");
        }

        try {
            fromSealed(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: sealed exhaustive");
        }

        try {
            modeNoNull(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: enum");
        }

        try {
            rejectNull(null);
        } catch (IllegalArgumentException e) {
            System.out.println("Đã từ chối: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac --release 21 NullSwitchDemo.java
java NullSwitchDemo
~~~

Đầu ra chính xác:

~~~text
NULL
Chuỗi trắng
Text: Java
Số: 42
S-1 đến Hà Nội
S-2 thiếu địa chỉ
S-3 đến không rõ
Kiểu khác
Null hoặc kiểu khác
Null hoặc kiểu khác
Đếm: 3
NPE: thiếu case null
NPE: Object pattern
NPE: sealed exhaustive
NPE: enum
Đã từ chối: value không được null
~~~

Các trường hợp chính:

1. `withNullCase(null)` trả `"NULL"` vì có nhãn null.
2. Guard `when s.isBlank()` áp dụng khi đối tượng thật sự là String; null không bị đẩy vào guard.
3. Nested record `Address(var city)` không khớp nếu **`Address` component** bằng null; nhánh `Shipment(..., var destination)` xử lý trường hợp đó.
4. Một `Address` tồn tại nhưng `city == null` vẫn có thể khớp nested record pattern và được xử lý ngay trong nhánh.
5. `case null, default` gom null và các giá trị ngoài String chung vào một phản hồi.
6. `catchAllObject(null)` vẫn ném NPE dù `Object` là kiểu rất rộng.
7. `fromSealed(null)` vẫn ném NPE dù switch exhaustive trên toàn bộ subtype của sealed interface.
8. `modeNoNull(null)` vẫn ném NPE dù đã xử lý cả hai enum constants.
9. `rejectNull(null)` cố ý ném `IllegalArgumentException` với thông điệp hợp đồng, thay vì NPE ngầm.

Các đoạn `catch` trong `main` chỉ để chương trình demo tiếp tục và quan sát từng tình huống lỗi; trong ứng dụng thực, đừng bắt mọi NPE rồi âm thầm bỏ qua.

## 12. Checklist gỡ lỗi: NPE thật sự từ đâu?

Khi log xuất hiện `NullPointerException` gần một `switch`, kiểm tra lần lượt:

1. **Giá trị selector có null không?** Tìm nguồn: method return, map lookup, JSON/DB nullable field, wrapper hoặc giá trị từ bên ngoài.
2. **Có `case null` không?** Đừng nhầm `default`, `case Object obj` hoặc exhaustiveness với null handling.
3. **NPE có xảy ra trước khi switch nhận selector không?** Ví dụ gọi `dto.status()` khi `dto == null`, hoặc unboxing một `Integer` null.
4. **NPE có thực sự từ code trong branch không?** Khi selector không null, field hoặc component dùng trong case vẫn có thể null; hãy kiểm tra cách truy cập `city.toUpperCase()`, `address.city()` và tương tự.
5. **Một nested record pattern có không khớp vì null không?** Nested record pattern không khớp null; cân nhắc nhánh record tổng quát và xử lý component null rõ ràng.
6. **Null có ý nghĩa domain không?** Nếu có, viết `case null` trả giá trị hợp lệ; nếu không, từ chối null ngay ở API boundary bằng thông báo rõ.
7. **Chính sách có được test không?** Viết test cho selector null, kiểu khác, record có component null, enum/wrapper null, và guard.

Ví dụ một hàm nhận dữ liệu từ tầng lưu trữ:

~~~java
static String statusLabel(String status) {
    return switch (status) {
        case null -> "Chưa thiết lập";
        case "NEW" -> "Mới";
        case "DONE" -> "Hoàn thành";
        default -> "Trạng thái không hỗ trợ";
    };
}
~~~

Nếu null đồng nghĩa “dữ liệu sai không được lưu”, thay `case null -> "Chưa thiết lập"` bằng `case null -> throw new IllegalArgumentException(...)`. Đừng tự động gán “chưa thiết lập” nếu domain yêu cầu trường này bắt buộc.

## 13. Lỗi thường gặp và cách sửa

| Hiểu sai | Hậu quả | Giải pháp |
| --- | --- | --- |
| `default` bắt tất cả, gồm null | Selector null ném NPE | Thêm `case null` hoặc kiểm tra trước switch |
| `case Object o` khớp null | NPE dù pattern được coi là bao quát non-null | Xử lý `case null` riêng |
| Switch exhaustive trên sealed interface không thể gây NPE | Selector null vẫn gây NPE | Phân biệt exhaustiveness với null-safety |
| Switch enum đã đủ mọi constant thì null cũng được | Enum reference null vẫn NPE | Có chính sách null rõ ràng |
| `case null, String s` là cách ghép null với String | Lỗi biên dịch `invalid case label combination` | Viết case riêng hoặc `case null, default` |
| Guard `when s == null` sẽ bắt null selector | Không có String pattern match, switch vẫn NPE | `case null` |
| `case null` tự bảo vệ mọi field của record | Vẫn có thể NPE khi thao tác component null | Kiểm tra null của từng component |
| `instanceof` null trả false nên pattern switch cũng thế | Hai cấu trúc có quy tắc khác nhau | Xem switch selector null như một trường hợp riêng |
| Chỉ dùng `try/catch (NullPointerException)` để xử lý | Có thể che bug ở code phía trong nhánh hoặc trước switch | Kiểm tra đầu vào, case null và nguyên nhân gốc |
| Thêm `default` vào mọi switch để tránh exception | Không xử lý null và có thể che thiếu subtype mới | Tận dụng exhaustiveness, xử lý null đúng chỗ |

## 14. Bài tập và đáp án định hướng

**Bài 1.** Vì sao đoạn sau ném NPE? Sửa theo hai cách khác nhau: (a) null trả `"empty"`, (b) null bị từ chối với `IllegalArgumentException`.

~~~java
static String test(Object value) {
    return switch (value) {
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}
~~~

**Bài 2.** Với `sealed interface Command permits Create, Delete {}`, compiler chấp nhận switch đủ hai subtype và không có `default`. Nếu selector là null, điều gì xảy ra? Vì sao đó không mâu thuẫn với exhaustiveness?

**Bài 3.** Cho `record Address(String city) {}` và `record Shipment(String id, Address destination) {}`. Viết switch expression xử lý riêng selector null, shipment có `destination == null`, và shipment có `destination.city() == null` mà không ném NPE.

**Bài 4.** Đoạn `case null, String s -> ...` có biên dịch không trong Java 21? Viết một nhánh thay thế hợp lệ để null và kiểu không phải String có cùng kết quả.

**Bài 5.** So sánh hai biểu thức:

~~~java
Object value = null;
boolean first = value instanceof String s;

String second = switch (value) {
    case String s -> s;
    default -> "other";
};
~~~

Giá trị `first` là gì? Biến `second` có nhận `"other"` không?

**Gợi ý đáp án:**

~~~java
// Bài 1(a):
static String safe(Object value) {
    return switch (value) {
        case null -> "empty";
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}

// Bài 1(b):
static String strict(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value null");
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}

// Bài 4: null và trường hợp không phải String dùng chung nhánh.
static String grouped(Object value) {
    return switch (value) {
        case String s -> s;
        case null, default -> "fallback";
    };
}
~~~

Bài 2: vẫn NPE vì selector null cần chính sách riêng. Bài 3: dùng `case null`, nested `Shipment(var id, Address(var city))` với điều kiện xử lý `city == null` và `Shipment(var id, var destination)` làm nhánh dự phòng. Bài 5: `first == false`, còn switch khi đánh giá `second` ném NPE trước khi có giá trị gán.

## Tóm tắt

Với một **`switch` trên reference selector**, hãy xem `null` là một quyết định về hợp đồng dữ liệu:

- **Null hợp lệ:** dùng `case null -> ...` (hoặc `case null, default -> ...` nếu hai trường hợp thực sự tương đương).
- **Null không hợp lệ:** từ chối rõ bằng `case null -> throw ...` hoặc kiểm tra ngay tại boundary.
- **Thiếu `case null`:** selector null làm switch ném NPE, bất kể `default`, `case Object` hay việc đã xử lý hết subtype của sealed hierarchy.
- **Null ở component/field:** cần được kiểm tra theo đường truy cập riêng; `case null` chỉ xử lý **selector**.

## Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): phần **Null case Labels**, dominance, exhaustive pattern switch và record patterns.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): quy tắc pattern switch và xử lý null ổn định trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns và nested component matching.
- [JLS 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11) và [§15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
