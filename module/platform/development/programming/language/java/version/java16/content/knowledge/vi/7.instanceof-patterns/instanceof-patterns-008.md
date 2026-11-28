# Pattern với generic và giới hạn do type erasure

## 1. Vì sao generic cần cách kiểm tra riêng?

Pattern matching for `instanceof` cho phép kiểm tra kiểu và khai báo biến trong cùng một biểu thức. Với kiểu thông thường, ta có thể viết:

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Nhưng với generic, không thể mặc định rằng mọi tham số kiểu đều còn tồn tại để JVM kiểm tra lúc chạy. Java dùng cơ chế *type erasure* (xóa thông tin tham số kiểu): trình biên dịch kiểm tra generic trong mã nguồn, sau đó xóa hoặc thay thế thông tin tham số kiểu theo quy tắc của ngôn ngữ khi tạo bytecode.

Vì vậy, từ Java 16, type pattern của `instanceof` phải dùng kiểu có thể kiểm tra lúc chạy (*reifiable type*). Quy tắc này vẫn áp dụng trong Java hiện đại.

## 2. Dùng `List<?>` để kiểm tra một danh sách

Khi chỉ biết một giá trị có thể là danh sách nhưng chưa biết kiểu phần tử, hãy dùng pattern `List<?>`:

~~~java
import java.util.List;

class GenericPatternInspection {
    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            System.out.println("Số phần tử: " + items.size());
        }
    }
}
~~~

Pattern `List<?> items` xác nhận đối tượng là một `List`. Dấu hỏi có nghĩa kiểu phần tử chưa được biết cụ thể. Biến `items` có kiểu tĩnh `List<?>`.

Khi đọc phần tử, kiểu tĩnh nhận được là `Object`:

~~~java
if (value instanceof List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

Trình biên dịch không cho phép sử dụng một phần tử như `String` chỉ vì danh sách hiện tại có vẻ chứa chuỗi. Cần kiểm tra từng phần tử trước khi gọi phương thức riêng của kiểu đó:

~~~java
if (value instanceof List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
~~~

Trong vòng lặp, pattern `String text` xác nhận từng phần tử. Những phần tử không phải chuỗi và phần tử `null` không đi vào nhánh này.

## 3. Vì sao `List<String>` không dùng được trong type pattern?

Đoạn sau không biên dịch:

~~~java
import java.util.List;

class InvalidGenericPattern {
    static void inspect(Object value) {
        // Lỗi biên dịch: List<String> không phải kiểu reifiable.
        // if (value instanceof List<String> names) {
        //     System.out.println(names.get(0));
        // }
    }
}
~~~

Ở thời điểm chạy, JVM có thể xác định đối tượng là một `List`, nhưng không thể xác nhận đối tượng đó là `List<String>` thay vì `List<Integer>`. Thông tin tham số kiểu `String` đã bị xóa theo cơ chế type erasure.

Hãy dùng `List<?>` để kiểm tra danh sách, sau đó xác nhận kiểu phần tử:

~~~java
import java.util.List;

class InspectStringElements {
    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            for (Object item : items) {
                if (item instanceof String text) {
                    System.out.println(text);
                }
            }
        }
    }
}
~~~

Điểm quan trọng: `List<?>` không khẳng định danh sách chỉ chứa chuỗi. Nó chỉ nói rằng đây là một danh sách với kiểu phần tử chưa biết.

## 4. Reifiable type và các kiểu generic được phép

Một kiểu *reifiable* là kiểu mà thông tin cần thiết để kiểm tra kiểu vẫn có thể xác định được ở runtime. Với generic, các dạng thường gặp có thể dùng trong type pattern gồm:

- Kiểu lớp hoặc giao diện không có tham số kiểu, ví dụ `String`, `Number`, `List`.
- Kiểu tham số hóa mà mọi đối số kiểu đều là wildcard không có bound, ví dụ `List<?>` hoặc `Map<?, ?>`.
- Kiểu raw như `List`. Kiểu raw vẫn tồn tại vì tương thích với mã Java cũ, nhưng nên ưu tiên wildcard để giữ an toàn kiểu.
- Mảng có kiểu phần tử reifiable, ví dụ `String[]`, `int[]` hoặc `List<?>[]`.

Các kiểu tham số hóa có wildcard giới hạn không phải reifiable:

~~~java
import java.util.List;

class BoundedWildcardPattern {
    static void inspect(Object value) {
        // Không hợp lệ: List<? extends Number> không phải reifiable.
        // if (value instanceof List<? extends Number> numbers) { ... }

        // Hợp lệ: wildcard không có bound.
        if (value instanceof List<?> items) {
            System.out.println(items.size());
        }
    }
}
~~~

`List<? extends Number>` mô tả một tập kiểu phần tử cụ thể hơn, nhưng runtime không giữ đủ thông tin để kiểm tra bound đó qua một đối tượng `Object`. Dùng `List<?>` trong pattern rồi kiểm tra từng phần tử nếu cần xác nhận chúng là số.

### 4.1. Type variable cũng không phải kiểu pattern reifiable

Một tham số kiểu như `T` được xác định khi biên dịch và bị xóa theo type erasure. Vì vậy, không thể dùng trực tiếp type variable làm kiểu pattern:

~~~java
class TypeVariablePatternDemo {
    static <T> boolean containsString(T value) {
        return value instanceof String text;
    }

    // Không hợp lệ: T không phải kiểu reifiable.
    // static <T> boolean matchesT(Object value) {
    //     return value instanceof T item;
    // }
}
~~~

Phương thức `containsString` hợp lệ vì nó kiểm tra một kiểu cụ thể có thể xác định lúc chạy là `String`. Ngược lại, JVM không thể kiểm tra `T` là kiểu gì ở runtime. Nếu cần xác nhận một lớp do caller chọn, có thể truyền `Class<T>` và dùng `isInstance`; cách này chỉ kiểm tra lớp có thể biểu diễn bằng đối tượng `Class`, không xác nhận tham số generic như `List<String>`.

## 5. Type erasure: điều gì còn lại khi chạy?

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

class TypeErasureDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List<Integer> scores = new ArrayList<>();

        System.out.println(names.getClass() == scores.getClass()); // true
    }
}
~~~

Hai biến có kiểu generic khác nhau trong mã nguồn, nhưng đều tạo đối tượng có lớp runtime là `ArrayList`. JVM không có hai lớp runtime riêng là `ArrayList<String>` và `ArrayList<Integer>`.

Trình biên dịch vẫn dùng thông tin generic để kiểm tra an toàn kiểu khi biên dịch. Khi cần, nó chèn các phép ép kiểu phù hợp tại nơi đọc giá trị. Tuy nhiên, thông tin tham số kiểu không trở thành điều kiện để `instanceof` kiểm tra một đối tượng lúc chạy.

Ví dụ sau vì thế không thể dùng để xác nhận kiểu phần tử:

~~~java
import java.util.ArrayList;
import java.util.List;

class ReadUnknownList {
    static void inspect() {
        Object value = new ArrayList<Integer>();

        if (value instanceof List<?> items) {
            // Chỉ biết đây là List; không thể kết luận List<Integer>.
            Object first = items.isEmpty() ? null : items.get(0);
            System.out.println(first);
        }
    }
}
~~~

## 6. `List<?>` giữ an toàn kiểu khi chưa biết phần tử

Khi dùng `List<?>`, có thể đọc phần tử dưới kiểu `Object`, nhưng không thể thêm một giá trị tùy ý như chuỗi vào danh sách:

~~~java
import java.util.List;

class UnknownElementType {
    static void inspect(List<?> items) {
        Object first = items.isEmpty() ? null : items.get(0);

        // Lỗi biên dịch: kiểu phần tử thực tế chưa được biết.
        // items.add("Java");
    }
}
~~~

Đây là cơ chế bảo vệ kiểu. Nếu danh sách thực tế là `List<Integer>`, cho phép thêm một `String` sẽ làm hỏng giả định kiểu của nơi đang sử dụng danh sách.

Không nhầm `List<?>` với `List<Object>`:

~~~java
import java.util.List;

class WildcardVsObjectList {
    static void acceptAnyList(List<?> values) {
        System.out.println(values.size());
    }

    static void acceptObjectList(List<Object> values) {
        System.out.println(values.size());
    }

    static void demo() {
        List<String> names = List.of("An", "Bình");

        acceptAnyList(names); // Hợp lệ
        // acceptObjectList(names); // Không hợp lệ
    }
}
~~~

Generic trong Java là bất biến (*invariant*): `List<String>` không phải subtype của `List<Object>`. Tuy nhiên, `List<String>` có thể truyền cho tham số `List<?>` vì wildcard chấp nhận danh sách với kiểu phần tử chưa biết.

## 7. Xác thực từng phần tử và tạo `List<String>` an toàn

Nếu ứng dụng cần một danh sách chuỗi đã được xác nhận, hãy tạo danh sách mới từ các phần tử đã kiểm tra. Không ép kiểu toàn bộ `List<?>` sang `List<String>`:

~~~java
import java.util.ArrayList;
import java.util.List;

class GenericInputValidator {
    static List<String> requireStrings(Object value) {
        if (!(value instanceof List<?> items)) {
            throw new IllegalArgumentException("Giá trị phải là một danh sách");
        }

        List<String> result = new ArrayList<>();

        for (Object item : items) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "Mọi phần tử phải là chuỗi và không được null");
            }
            result.add(text);
        }

        return List.copyOf(result);
    }

    static List<String> onlyStrings(Object value) {
        if (!(value instanceof List<?> items)) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        for (Object item : items) {
            if (item instanceof String text) {
                result.add(text);
            }
        }
        return List.copyOf(result);
    }
}
~~~

Hai phương thức trong `GenericInputValidator` minh họa hai chính sách khác nhau:

- `requireStrings` xác nhận giá trị là danh sách, kiểm tra từng phần tử bằng `instanceof String text` và báo lỗi nếu có phần tử sai kiểu hoặc `null`.
- `onlyStrings` chỉ giữ phần tử khớp với `String`, bỏ qua phần tử sai kiểu và `null`.

Cả hai tạo một `List<String>` mới rồi trả về bản sao không thể sửa đổi bằng `List.copyOf`. API này có từ Java 10 và tiếp tục được hỗ trợ trong Java hiện đại. Danh sách mới cũng tránh phụ thuộc vào một danh sách bên ngoài có thể tiếp tục bị thay đổi sau khi kiểm tra.

## 8. Khi nào nên dùng wildcard và khi nào nên kiểm tra từng phần tử?

| Nhu cầu | Cách làm |
| --- | --- |
| Chỉ cần biết giá trị là một danh sách | `value instanceof List<?> items` |
| Chỉ cần duyệt và đọc phần tử | Duyệt `List<?>` với biến phần tử kiểu `Object` |
| Cần xử lý riêng phần tử chuỗi | Kiểm tra từng phần tử bằng `item instanceof String text` |
| Cần xác nhận mọi phần tử là chuỗi | Duyệt, kiểm tra và từ chối nếu có phần tử không đúng kiểu |
| Cần lấy danh sách chuỗi đã xác thực | Tạo `List<String>` mới từ các phần tử đã kiểm tra |
| Muốn kiểm tra trực tiếp `List<String>` ở runtime | Không thể dựa vào type pattern vì tham số kiểu đã bị xóa |

Không nên dùng raw type hoặc ép kiểu không kiểm tra để né giới hạn của type erasure. Những cách đó có thể đưa lỗi kiểu đến thời điểm sử dụng phần tử, nơi lỗi khó tìm hơn. Dùng `List<?>` và xác thực phần tử giúp ranh giới dữ liệu rõ ràng, giữ được kiểm tra kiểu của trình biên dịch.

**Ghi nhớ:** Generic type arguments không được giữ đầy đủ ở runtime. Vì vậy, pattern nên kiểm tra `List<?>` để xác nhận cấu trúc danh sách, rồi kiểm tra từng phần tử khi cần kiểu cụ thể. Đây là cách tương thích với type erasure và vẫn an toàn kiểu trong Java hiện đại.
