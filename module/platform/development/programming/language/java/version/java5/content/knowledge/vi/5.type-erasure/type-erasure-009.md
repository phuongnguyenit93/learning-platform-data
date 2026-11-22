# Giới hạn kiểm tra `instanceof` đối với đối số kiểu

## 1. Cần phân biệt hai câu hỏi

Với một giá trị nhận dưới dạng `Object`, hai câu hỏi sau khác nhau:

1. Đối tượng này có phải một danh sách không?
2. Đối tượng này có đáp ứng yêu cầu mọi phần tử là chuỗi không?

`instanceof List<?>` giải quyết câu hỏi thứ nhất. Nó không tự giải quyết câu hỏi thứ hai.

Đối số kiểu như `String` trong `List<String>` được dùng chủ yếu để kiểm tra mã nguồn. Với một đối tượng danh sách generic thông thường, lớp thực thi không mang một danh tính riêng cho mỗi đối số kiểu. Hai đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` vẫn có cùng lớp thực thi `ArrayList`.

Vì vậy, không thể yêu cầu một phép kiểm tra lớp từ `Object` đồng thời khôi phục toàn bộ hợp đồng đối số kiểu đã bị xóa. Muốn xác thực các giá trị, cần kiểm tra dữ liệu hoặc nhận thông tin từ một hợp đồng tĩnh đủ mạnh.

Bài dùng Java 17 trở lên và theo quy tắc hiện đại trong [JLS §15.20.2 về instanceof](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2).

## 2. Bắt đầu từ `Object`: kiểm tra bằng wildcard không giới hạn

Đây là cách hợp lệ để nhận diện một danh sách mà chưa khẳng định kiểu phần tử:

```java
Object candidate = List.of("A", "B");

if (candidate instanceof List<?> values) {
    System.out.println(values.size());
    Object first = values.get(0);
}
```

Khi điều kiện đúng, pattern matching cung cấp biến `values` có kiểu `List<?>`. Có thể lấy kích thước, duyệt và đọc phần tử dưới dạng `Object`.

Nhưng các bước sau không tự trở thành hợp lệ:

```java
if (candidate instanceof List<?> values) {
    // List<String> strings = values; // Không đủ quan hệ kiểu.
    // String first = values.get(0);  // Chưa biết phần tử là String.
    // values.add("C");              // Chưa biết kiểu phần tử để thêm.
}
```

Biến pattern giúp dùng đối tượng với kiểu đã kiểm tra; nó không tạo thêm bằng chứng về những đối số kiểu chưa được kiểm chứng.

Nếu `candidate` là `null`, điều kiện `instanceof` cho kết quả `false`. Nếu `candidate` là một chuỗi đứng riêng, kiểm tra `List<?>` cũng cho `false`. Đây là kết quả của biểu thức hợp lệ khi chạy, khác với một biểu thức bị từ chối ngay khi biên dịch.

## 3. Các kiểm tra bị cấm từ `Object`

Những ví dụ sau là các dòng minh họa lỗi, không phải mã chạy:

```java
Object candidate = List.of("A");

// boolean a = candidate instanceof List<String>;
// boolean b = candidate instanceof List<Object>;
// boolean c = candidate instanceof List<? extends Number>;
// boolean d = candidate instanceof List<List<String>>;
```

Lý do không nằm ở việc “danh sách hiện tại có vẻ chứa chuỗi” hay không. Kiểu tĩnh bên trái là `Object`, nên phép kiểm tra không có bằng chứng sẵn về đối số kiểu. JVM không thể kiểm tra toàn bộ các hợp đồng này bằng nhận diện lớp thông thường.

`List<Object>` cũng không phải cách viết thay thế cho “mọi danh sách”. Nó biểu đạt một đối số kiểu cụ thể. Còn `List<? extends Number>` vẫn đòi hỏi một quan hệ với kiểu phần tử, chứ không chỉ yêu cầu đối tượng thuộc `List`.

Với cấu trúc nhiều đối số kiểu:

```java
Object candidate = Map.of("A", 1);
boolean isMap = candidate instanceof Map<?, ?>; // Hợp lệ.
// boolean stringKeys = candidate instanceof Map<String, ?>; // Bị từ chối.
```

Một đối số kiểu `String` chưa thể kiểm tra là đủ để không thể xác nhận hợp đồng thứ hai từ `Object`.

Các đoạn minh họa cần import các kiểu thư viện chuẩn tương ứng khi đặt vào lớp Java.

## 4. Vai trò của kiểu reifiable

Một kiểu reifiable có đủ thông tin tương ứng còn khả dụng lúc chạy. `List<?>` là reifiable vì nó không yêu cầu nhận diện một kiểu phần tử cụ thể. `List<String>` không reifiable vì đối số `String` của danh sách bị xóa khỏi danh tính lớp của đối tượng.

Các ví dụ hữu ích khi kiểm tra từ `Object`:

| Kiểu đích | Ý nghĩa kiểm tra | Có thể dùng trong ví dụ bắt đầu từ `Object`? |
| --- | --- | --- |
| `String` | Đối tượng là chuỗi | Có |
| `List<?>` | Đối tượng là danh sách, không khẳng định kiểu phần tử | Có |
| `Map<?, ?>` | Đối tượng là ánh xạ, không khẳng định kiểu khóa/giá trị | Có |
| `List<String>` | Đòi hỏi đối số kiểu cụ thể của danh sách | Không |
| `List<? extends Number>` | Đòi hỏi quan hệ cận của kiểu phần tử | Không |
| `List<?>[]` | Đối tượng là mảng có kiểu thành phần danh sách tương ứng | Có |
| `List<String>[]` | Đòi hỏi kiểu phần tử generic cụ thể cho danh sách con | Không |

Định nghĩa reifiable trong [JLS §4.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7) giúp hiểu những thông tin nào không bị mất theo cách ảnh hưởng tới phép kiểm tra.

Tuy nhiên, không nên biến khái niệm này thành quy tắc “chỉ kiểu reifiable mới có thể xuất hiện sau `instanceof` trong mọi ngữ cảnh”. Java hiện đại còn sử dụng bằng chứng từ kiểu tĩnh bên trái.

## 5. Trường hợp hiện đại hợp lệ nhờ kiểu tĩnh đã có

Xét:

```java
List<String> values = new ArrayList<>(List.of("A"));

if (values instanceof ArrayList<String> concrete) {
    System.out.println(concrete.size());
}
```

Đây là mã hợp lệ trên Java 17 trở lên, dù `ArrayList<String>` không phải kiểu reifiable.

Lý do là `values` đã mang hợp đồng tĩnh `List<String>`. Điều cần phân biệt thêm khi chạy là lớp triển khai của danh sách có phải `ArrayList` hay không. Quan hệ kiểu phần tử được giữ từ khai báo đã có, không được phát hiện bằng cách quét dữ liệu.

Đối chiếu ba ngữ cảnh:

| Kiểu tĩnh của biến `x` | Phép kiểm tra | Kết quả kiểm tra khi biên dịch |
| --- | --- | --- |
| `Object` | `x instanceof ArrayList<String>` | Bị từ chối vì thiếu bằng chứng về đối số kiểu |
| `List<String>` | `x instanceof ArrayList<String>` | Hợp lệ |
| `List<Integer>` | `x instanceof ArrayList<String>` | Bị từ chối vì quan hệ kiểu không tương thích |

Ở dòng hợp lệ, kết quả khi chạy vẫn có thể là `true` hoặc `false`, tùy đối tượng triển khai. Nếu biến `List<String>` đang trỏ đến một danh sách triển khai khác, việc kiểm tra `ArrayList<String>` cho `false`; nếu giá trị là `null`, cũng cho `false`.

Nguyên tắc cần giữ là: phép kiểm tra phải phù hợp với thông tin kiểu tĩnh và không đòi hỏi một phép chuyển đổi unchecked để xác nhận kiểu đích. Đừng nhìn riêng phần `ArrayList<String>` mà bỏ qua khai báo của `x`.

Mã nguồn đã phá vỡ an toàn kiểu bằng cast unchecked có thể làm hợp đồng tĩnh không còn phản ánh dữ liệu đúng. Phép kiểm tra lớp triển khai không có trách nhiệm dò tìm và sửa những vi phạm đó bằng cách kiểm tra mọi phần tử.

## 6. Pattern matching không làm xuất hiện cơ chế kiểm tra sâu

Hai cách viết sau có cùng giới hạn về đối số kiểu:

```java
if (candidate instanceof List<?>) {
    // Đã biết candidate là một List.
}

if (candidate instanceof List<?> values) {
    // Có thêm biến values mang kiểu List<?> trong phạm vi phù hợp.
}
```

Cách thứ hai tiện hơn vì có biến được liên kết trực tiếp với điều kiện đúng. Nó không tự xác thực phần tử hay loại bỏ mọi vấn đề do xóa kiểu.

Với danh sách lồng nhau, kiểm tra ngoài cùng không nói gì về cấu trúc của từng phần tử:

```java
if (candidate instanceof List<?> outer) {
    for (Object item : outer) {
        if (item instanceof List<?> inner) {
            // Chỉ tại đây mới biết item là một danh sách con.
            // Muốn biết các giá trị của inner là String thì cần kiểm tra tiếp.
        }
    }
}
```

Một phép kiểm tra nông không thay thế một bộ xác thực dữ liệu lồng nhau. Những ràng buộc như khóa có định dạng nào, danh sách được rỗng không, phần tử có được `null` không đều thuộc hợp đồng dữ liệu riêng.

## 7. Cách xác thực các giá trị chuỗi một cách rõ ràng

Nếu yêu cầu thực sự là “mọi phần tử đang có đều là chuỗi khác `null`”, hãy kiểm tra từng phần tử sau khi xác nhận `List<?>`:

```java
static boolean hasOnlyNonNullStrings(Object candidate) {
    if (!(candidate instanceof List<?> values)) {
        return false;
    }
    for (Object value : values) {
        if (!(value instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Hàm này chấp nhận danh sách rỗng vì không có phần tử vi phạm; từ chối phần tử `null` vì `null instanceof String` là `false`. Đây là lựa chọn hợp đồng cần được nêu rõ, không phải một kết luận duy nhất cho mọi bài toán.

Kết quả `true` chỉ nói về các giá trị đã quan sát trong lần duyệt. Nó không phát hiện một đối số kiểu được lưu trên danh sách. Một danh sách được khai báo `List<Object>` nhưng hiện chỉ chứa chuỗi vẫn có thể vượt qua phép kiểm tra này.

Nếu giữ danh sách gốc có thể thay đổi, một tham chiếu khác có thể thêm giá trị khác sau khi kiểm tra. Vì vậy, ở ranh giới dữ liệu, nên cân nhắc tạo bản sao có kiểu từ những giá trị đã kiểm tra. Chương trình tiếp theo làm việc đó mà không dùng cast unchecked.

Với danh sách lớn, xác thực toàn bộ có chi phí theo số phần tử; đó là công việc khác với kiểm tra lớp. Cũng cần có quy tắc về sửa đổi đồng thời nếu dữ liệu có thể thay đổi trong lúc duyệt.

## 8. Chương trình hoàn chỉnh

Lưu vào `InstanceofTypeArgumentsDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class InstanceofTypeArgumentsDemo {
    static String describe(Object candidate) {
        if (!(candidate instanceof List<?> values)) {
            return "not a list";
        }
        boolean allStrings = true;
        for (Object value : values) {
            if (!(value instanceof String)) {
                allStrings = false;
                break;
            }
        }
        return "list size=" + values.size() + ", all non-null strings=" + allStrings;
    }

    static List<String> checkedStringCopy(Object candidate) {
        if (!(candidate instanceof List<?> values)) {
            throw new IllegalArgumentException("Expected a list");
        }
        List<String> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected non-null strings");
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object strings = new ArrayList<String>(List.of("A", "B"));
        Object integers = new ArrayList<Integer>(List.of(1, 2));
        System.out.println("same runtime class = " + strings.getClass().equals(integers.getClass()));
        System.out.println(describe(strings));
        System.out.println(describe(integers));
        System.out.println(describe(List.of("A", 1)));
        System.out.println(describe(List.of()));
        System.out.println(describe(Arrays.asList("A", null)));
        System.out.println(describe(null));
        System.out.println(describe("A"));

        List<String> known = new ArrayList<>(List.of("known"));
        if (known instanceof ArrayList<String> concrete) {
            System.out.println("refined implementation size = " + concrete.size());
        }

        System.out.println("checked copy = " + checkedStringCopy(strings));
        try {
            checkedStringCopy(integers);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected integer values");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked -encoding UTF-8 InstanceofTypeArgumentsDemo.java
java InstanceofTypeArgumentsDemo
```

Kết quả chuẩn:

```text
same runtime class = true
list size=2, all non-null strings=true
list size=2, all non-null strings=false
list size=2, all non-null strings=false
list size=0, all non-null strings=true
list size=2, all non-null strings=false
not a list
not a list
refined implementation size = 1
checked copy = [A, B]
rejected integer values
```

Các dòng kết quả lần lượt chứng minh:

- Hai `ArrayList` có đối số kiểu khác nhau vẫn có cùng lớp thực thi.
- Danh sách chuỗi, số, hỗn hợp, rỗng và chứa `null` đều có thể vượt qua bước nhận diện `List<?>`, nhưng kết quả xác thực phần tử khác nhau.
- `null` và một chuỗi đứng riêng không phải danh sách.
- Thông tin tĩnh `List<String>` cho phép thu hẹp sang lớp triển khai `ArrayList<String>`.
- Kết quả `List<String>` của `checkedStringCopy` được xây từ các giá trị đã kiểm tra; danh sách số bị từ chối theo hợp đồng của hàm.

`List.copyOf(result)` trả một danh sách không cho sửa và không chứa `null` theo các điều kiện đã kiểm tra. Hàm không có quyền tác động lên những tham chiếu khác của danh sách nguồn, nhưng kết quả tạo mới không phụ thuộc vào việc thêm/xóa phần tử trên danh sách nguồn sau đó. Ví dụ giả định nguồn không bị sửa đồng thời trong lúc duyệt.

## 9. Quan sát bytecode để biết JVM đang kiểm tra gì

Chạy:

```shell
javap -c InstanceofTypeArgumentsDemo
```

Trong phương thức `describe`, phép kiểm tra danh sách có lệnh chính dạng:

```text
instanceof java/util/List
```

Trong vòng lặp kiểm tra phần tử, có lệnh riêng:

```text
instanceof java/lang/String
```

Và trường hợp thu hẹp lớp triển khai ở `main` có:

```text
instanceof java/util/ArrayList
```

Đây là các trích rút gọn, đã bỏ offset và chỉ số constant pool. Điểm cần nhận ra: không có một lệnh riêng “kiểm tra đối tượng này là `List<String>` và kiểm tra mọi phần tử của nó”. Việc nhận diện danh sách và xác thực phần tử là những phần việc khác nhau trong mã.

Không cần kiểm tra bytecode trong mọi lần viết ứng dụng. Nó hữu ích khi cần kiểm chứng mô hình xóa kiểu và tránh suy luận rằng cú pháp generic trong một phép kiểm tra hợp lệ nhất thiết đã trở thành nhãn kiểu đầy đủ ở JVM.

## 10. Không thay giới hạn `instanceof` bằng ép kiểu thiếu kiểm tra

Đoạn sau chỉ là minh họa một hướng xử lý cần tránh:

```java
if (candidate instanceof List<?>) {
    // List<String> values = (List<String>) candidate;
    // Cast này cần cảnh báo unchecked; bước kiểm tra List<?> chưa chứng minh String.
}
```

Cast không duyệt phần tử. Ẩn cảnh báo bằng `@SuppressWarnings` cũng không tạo bằng chứng mới. Nếu dữ liệu thực chứa số, lỗi có thể xuất hiện muộn hơn khi nơi gọi lấy phần tử như `String`.

Cần chọn giải pháp theo tình huống:

- Trong mã nội bộ đã có hợp đồng kiểu rõ: giữ kiểu generic từ đầu thay vì hạ xuống `Object` rồi cố đoán lại.
- Chỉ cần thao tác không phụ thuộc kiểu phần tử: nhận và dùng `List<?>`.
- Nhận dữ liệu chưa được xác thực: kiểm tra hình dạng và các giá trị, rồi tạo kết quả có kiểu rõ ràng.
- Cần kiểm tra một lớp cụ thể do nơi gọi quyết định: cân nhắc truyền `Class<T>`. Token `String.class` kiểm tra được chuỗi, nhưng `List.class` vẫn chỉ kiểm tra được danh sách, không kiểm tra đối số kiểu.

Metadata generic đọc qua reflection mô tả các khai báo, không tự chứng minh mọi giá trị trong một đối tượng tùy ý. Đừng dùng việc thấy `List<String>` trong metadata như một phép thay thế cho xác thực dữ liệu tại ranh giới.

## 11. Tự kiểm tra

**Câu 1.** `Object x = List.of(1, 2);` có vượt qua `x instanceof List<?>` không?

Có. Phép kiểm tra chỉ yêu cầu đối tượng là danh sách, không yêu cầu kiểu phần tử cụ thể.

**Câu 2.** Từ biến `Object x`, `x instanceof List<String>` cho `false` khi danh sách chứa số hay gây lỗi biên dịch?

Gây lỗi biên dịch. Đây không phải một biểu thức hợp lệ để chạy rồi trả `false`.

**Câu 3.** Vì sao `List<String> x` có thể kiểm tra `x instanceof ArrayList<String>`?

Quan hệ phần tử `String` đã được cung cấp bởi kiểu tĩnh. Khi chạy chỉ cần phân biệt lớp triển khai tương ứng; không cần khám phá kiểu phần tử từ đầu.

**Câu 4.** Một hàm duyệt và thấy mọi phần tử là `String` có chứng minh danh sách đã được khai báo `List<String>` không?

Không. Nó chỉ xác nhận các giá trị đã quan sát thỏa điều kiện. Cách khai báo ban đầu có thể khác, và nguồn có thể thay đổi sau đó nếu còn tham chiếu có quyền sửa.

**Câu 5.** Pattern `instanceof List<?> values` có cho phép thêm một chuỗi bất kỳ vào `values` không?

Không. Nó vẫn là danh sách có kiểu phần tử chưa biết. Kiểm tra được lớp của đối tượng không tự mở rộng quyền ghi đối với kiểu phần tử.
