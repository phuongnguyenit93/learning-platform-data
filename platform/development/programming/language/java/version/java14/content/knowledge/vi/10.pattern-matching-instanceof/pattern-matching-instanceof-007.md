# Giới hạn đối với kiểu generic không kiểm tra được lúc chạy trong mẫu instanceof

**`instanceof` với type pattern** cho phép Java vừa kiểm tra kiểu đối tượng vừa khai báo một biến có kiểu tương ứng, ví dụ `if (value instanceof String text)`. Tuy nhiên, khi áp dụng cho **generic** như `List<String>`, ta phải phân biệt **kiểu tĩnh mà trình biên dịch biết** với **thông tin kiểu còn tồn tại khi chạy**. Java sử dụng *type erasure* cho phần lớn thông tin về type arguments của generic; do đó không thể yêu cầu JVM kiểm chứng trực tiếp rằng một đối tượng bất kỳ thực sự là `List<String>` chỉ bằng `instanceof`.

Trong module Java 14, pattern matching for `instanceof` từng là tính năng thử nghiệm. **Nội dung còn áp dụng hiện nay:** nó đã chính thức từ **Java 16** (JEP 394), nên các ví dụ bên dưới dùng **Java 17+**, không cần cờ preview. Một chi tiết quan trọng của Java 16+ là **không phải mọi kiểu generic không reifiable đều bị cấm tuyệt đối trong `instanceof`**: khi kiểu tĩnh của biểu thức bên trái cho phép một *casting conversion* kiểm tra hợp lệ đến kiểu đích, một số biểu thức vẫn được chấp nhận. Điều này **không tạo ra khả năng kiểm tra type arguments tại runtime**.

## 1. Vì sao type erasure giới hạn việc kiểm tra?

Khai báo sau thể hiện các **kiểu tĩnh** khác nhau:

~~~java
List<String> names = List.of("An", "Binh");
List<Integer> counts = List.of(1, 2);
~~~

Đây là đoạn mã minh họa đặt trong phương thức đã `import java.util.List;`. Trình biên dịch dùng type arguments `String` và `Integer` để giới hạn cách gọi `get`, `add` và những phương thức generic. Nhưng ở runtime, thông tin `List<String>` hay `List<Integer>` của **một instance collection cụ thể** không trở thành hai lớp JVM riêng biệt. Việc kiểm tra kiểu của đối tượng tập trung vào lớp/interface runtime, chẳng hạn `ArrayList` hoặc `List`, chứ không thể nhìn vào từng phần tử và chứng minh trực tiếp thông qua `instanceof`.

Ví dụ, hai lời gọi `new ArrayList<String>()` và `new ArrayList<Integer>()` đều tạo các đối tượng thuộc lớp runtime `java.util.ArrayList`. JVM không có hai lớp chuyên biệt `ArrayList<String>` và `ArrayList<Integer>` tương ứng.

**Hệ quả:** `instanceof List<?>` có thể xác định một giá trị không-null có triển khai `List` hay không; nó **không chứng minh** list chứa toàn `String`, toàn `Integer`, hay thậm chí đang chứa phần tử nào.

## 2. Reifiable và non-reifiable

Một kiểu **reifiable** là kiểu có đủ thông tin để xác định tại runtime theo quy tắc ngôn ngữ. Các kiểu generic với type arguments cụ thể thường **không reifiable**, trong khi generic chỉ dùng wildcard không giới hạn thường **reifiable**.

| Kiểu | Reifiable? | Ý nghĩa khi dùng với `instanceof` |
|---|---|---|
| `String` | Có | JVM nhận diện kiểu lớp cụ thể |
| `List` (raw type) | Có | Chỉ nhận diện `List`; không an toàn kiểu generic, nên không ưu tiên raw type |
| `List<?>` | Có | Có thể kiểm tra một đối tượng có là `List` và gán biến kiểu `List<?>` |
| `Map<?, ?>` | Có | Kiểm tra một đối tượng có là `Map` mà không bảo đảm kiểu key/value |
| `List<String>` | Không | Không thể kiểm tra riêng chữ `String` từ runtime class của list |
| `List<? extends Number>` | Không | Bound `Number` là thông tin generic không thể kiểm tra trực tiếp bằng phép kiểm tra instance từ `Object` |
| `List<?>[]` | Có | Mảng có kiểu phần tử reifiable |
| `List<String>[]` | Không | Mảng có kiểu phần tử generic không reifiable |

**Không hiểu “không reifiable” là “không bao giờ viết được trong `instanceof`”.** Trong Java 16+, việc biên dịch còn xét **kiểu tĩnh của toán hạng trái** và khả năng *casting conversion*; ví dụ nâng cao ở mục 5 là một trường hợp hợp lệ. Tuy vậy, không có phép thử runtime nào tự kiểm tra từng type argument cụ thể của một list.

### Tại sao `List<?>` tốt hơn `List`?

`List<?>` giữ lại cách làm việc an toàn với generic: có thể lấy phần tử dưới dạng `Object`, duyệt qua list hoặc đọc `size()`, nhưng không thể thêm tùy ý một `String` hoặc `Integer` vào list vì kiểu phần tử thật chưa được biết. Raw `List` làm mất nhiều kiểm tra generic của trình biên dịch và có thể dẫn tới cảnh báo *unchecked*.

## 3. Mẫu instanceof hợp lệ từ một Object

Khi nhận một giá trị có kiểu tĩnh `Object` (ví dụ từ API trả dữ liệu không đồng nhất), cách viết thông thường là:

~~~java
static String describe(Object input) {
    if (input instanceof List<?> values) {
        return "list(size=" + values.size() + ")";
    }
    return "not-list";
}
~~~

Đây là một phương thức **minh họa**, cần `import java.util.List;` và đặt bên trong một class.

- Java kiểm tra rằng `input` không-null và là một đối tượng triển khai `List`.
- Nếu mẫu khớp, biến mẫu `values` có kiểu tĩnh `List<?>` và được khởi tạo từ `input`.
- Nếu không khớp, nhánh `if` không chạy.
- Không có kiểm tra nội dung từng phần tử.

**Tại sao không viết như sau?**

~~~java
// CỐ Ý SAI: không biên dịch nếu input có kiểu tĩnh Object.
static boolean wrong(Object input) {
    return input instanceof List<String> names;
}
~~~

Ở đây, kiểu tĩnh `Object` không cung cấp bằng chứng generic về `String`, còn phép kiểm tra runtime không thể xác nhận type argument cụ thể. Do đó mẫu `List<String> names` không tương thích với biểu thức `Object` trong trường hợp này.

Với một đối tượng `Object input`, cả dạng pattern `input instanceof List<String> names` và dạng so sánh kiểu `input instanceof List<String>` đều không phải cách hợp lệ để yêu cầu kiểm chứng type argument `String`.

### Ví dụ không có dấu hỏi nhưng vẫn không đúng

~~~java
// CỐ Ý SAI: không biên dịch.
Object input = List.of("a");
if (input instanceof List<Integer> numbers) {
    System.out.println(numbers.size());
}
~~~

Lỗi không phụ thuộc vào nội dung thực tế của `List.of("a")`: dù compiler biết phần tạo đối tượng phía bên phải chứa chuỗi, biến `input` được khai báo `Object`, và Java không thể dùng runtime `instanceof` để chứng minh kiểu `List<Integer>`.

## 4. Kiểm tra nội dung nếu thật sự cần List<String>

Nếu yêu cầu nghiệp vụ là “đầu vào phải là list gồm toàn chuỗi”, hãy **kiểm tra hai tầng**:

1. `input instanceof List<?> list` để kiểm tra cấu trúc collection.
2. Duyệt các phần tử, áp dụng `element instanceof String text` cho **từng phần tử**.

Sau đó, thay vì ép kiểu toàn bộ danh sách bằng unchecked cast, hãy tạo một `List<String>` mới từ những chuỗi đã kiểm tra.

~~~java
static List<String> requireStrings(Object input) {
    if (!(input instanceof List<?> items)) {
        throw new IllegalArgumentException("not a list");
    }

    List<String> result = new ArrayList<>();
    for (Object element : items) {
        if (element instanceof String text) {
            result.add(text);
        } else {
            throw new IllegalArgumentException("non-string element");
        }
    }
    return List.copyOf(result);
}
~~~

Đây là một **phương thức minh họa** đặt trong class đã import `java.util.List` và `java.util.ArrayList`. Nó không cần ép kiểu unchecked. Nếu có phần tử `null`, mẫu `instanceof String` không khớp nên phương thức cũng từ chối. Với list rỗng, vòng lặp không gặp phần tử sai nên trả một danh sách chuỗi rỗng: kết quả hợp lý khi ta định nghĩa điều kiện là “mọi phần tử, nếu có, đều là chuỗi”.

**Lưu ý về thời điểm kiểm tra:** Đoạn mã trên tạo danh sách mới sau khi kiểm tra từng phần tử. Nếu nguồn là collection mutable đang bị thay đổi đồng thời, cần xác định cách đồng bộ hoặc lấy bản chụp thích hợp. Một lần duyệt không tự biến collection nguồn thành bất biến hay đảm bảo không có race condition.

## 5. Điểm tinh tế từ Java 16+: một số non-reifiable type pattern vẫn hợp lệ

Không nên dạy quy tắc cũ theo kiểu “`instanceof` chỉ cho phép kiểu reifiable trong mọi trường hợp”. Quy tắc đó **đã được nới trong Java 16**.

Xét:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));

if (numbers instanceof ArrayList<Integer> arrayList) {
    System.out.println(arrayList.size());
}
~~~

Đây là đoạn **hợp lệ trên Java 17+** khi đã import `java.util.List` và `java.util.ArrayList`.

Vì sao được chấp nhận?

- Biểu thức bên trái có **kiểu tĩnh `List<Integer>`**: phần `Integer` đã được thể hiện trong hợp đồng kiểu của chính biến đầu vào.
- Mẫu bên phải có kiểu `ArrayList<Integer>`. Java có *casting conversion* hợp lệ từ `List<Integer>` đến `ArrayList<Integer>`.
- Kiểm tra runtime xác nhận đối tượng là `ArrayList`; kết hợp với thông tin tĩnh sẵn có, compiler cho phép biến mẫu có kiểu `ArrayList<Integer>`.
- JVM **không duyệt các phần tử để xác nhận chúng là Integer**. Nếu chương trình đã gây *heap pollution* thông qua raw/unchecked operations, thông tin tĩnh có thể không phản ánh nội dung thật và lỗi vẫn có thể xuất hiện ở chỗ đọc phần tử.

**Trường hợp tương phản, không hợp lệ:**

~~~java
// CỐ Ý SAI: List<Integer> không chuyển kiểu hợp lệ
// sang ArrayList<String> trong phép kiểm tra này.
List<Integer> numbers = new ArrayList<>(List.of(10, 20));

if (numbers instanceof ArrayList<String> strings) {
    System.out.println(strings.size());
}
~~~

`Integer` và `String` là hai type arguments không tương thích trong trường hợp này. Java không thể suy ra một phép chuyển kiểu an toàn từ kiểu tĩnh `List<Integer>` sang `ArrayList<String>`.

| Biểu thức (Java 17) | Kiểu tĩnh bên trái | Kết quả biên dịch | Vì sao |
|---|---|---|---|
| `input instanceof List<?> list` | `Object` | Hợp lệ | `List<?>` reifiable |
| `input instanceof List<String> list` | `Object` | Lỗi | Không có kiểm tra an toàn type argument `String` |
| `numbers instanceof ArrayList<Integer> a` | `List<Integer>` | Hợp lệ | Có casting conversion phù hợp từ kiểu tĩnh |
| `numbers instanceof ArrayList<String> a` | `List<Integer>` | Lỗi | Không có casting conversion tương thích |
| `input instanceof String text` | `Object` | Hợp lệ | Kiểu `String` nhận diện được tại runtime |

**Kết luận chính xác:** Việc kiểu ở bên phải non-reifiable **không tự quyết định** hợp lệ hay không trong Java 16+; cần xét cả kiểu tĩnh bên trái và quy tắc *casting conversion*. Nhưng sự cho phép của compiler tuyệt đối **không hàm ý** JVM có khả năng xác thực nội dung type arguments tại runtime.

## 6. Chương trình Java 17+ đầy đủ, chạy được

Tạo file **`GenericInstanceofLimitsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericInstanceofLimitsDemo {

    static String describe(Object input) {
        if (!(input instanceof List<?> list)) {
            return "not-list";
        }

        int stringCount = 0;
        for (Object element : list) {
            if (element instanceof String text && !text.isBlank()) {
                stringCount++;
            }
        }
        return "list(size=" + list.size()
                + ", nonblankStrings=" + stringCount + ")";
    }

    static List<String> requireStrings(Object input) {
        if (!(input instanceof List<?> items)) {
            throw new IllegalArgumentException("not a list");
        }

        List<String> result = new ArrayList<>();
        for (Object element : items) {
            if (element instanceof String text) {
                result.add(text);
            } else {
                throw new IllegalArgumentException(
                        "non-string element"
                );
            }
        }
        return List.copyOf(result);
    }

    static String refined(List<Integer> numbers) {
        // Hợp lệ trong Java 17 vì kiểu tĩnh bên trái là List<Integer>.
        if (numbers instanceof ArrayList<Integer> arrayList) {
            int sum = 0;
            for (Integer value : arrayList) {
                sum += value;
            }
            return "array-list(sum=" + sum + ")";
        }
        return "not-array-list";
    }

    public static void main(String[] args) {
        Object mixed = List.of("java", 7, "pattern");
        Object notList = "java";

        System.out.println(describe(mixed));
        System.out.println(describe(notList));
        System.out.println(requireStrings(List.of("a", "b")));

        try {
            requireStrings(mixed);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        List<Integer> numbers =
                new ArrayList<>(List.of(2, 3));
        System.out.println(refined(numbers));
    }
}
~~~

Chạy tại thư mục chứa file với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 GenericInstanceofLimitsDemo.java
java GenericInstanceofLimitsDemo
~~~

**Standard output:**

~~~text
list(size=3, nonblankStrings=2)
not-list
[a, b]
invalid=non-string element
array-list(sum=5)
~~~

### Phân tích từng dòng

1. `describe(mixed)` nhận một `List<?>` có ba phần tử. Trong vòng lặp, hai phần tử `"java"` và `"pattern"` khớp mẫu `String text` và không blank, còn số `7` không khớp.
2. `describe(notList)` nhận chuỗi, không phải danh sách, nên trả `not-list`.
3. `requireStrings(List.of("a", "b"))` đi qua hai kiểm tra `String` và xây một danh sách `List<String>` mới; `List.toString()` hiển thị `[a, b]`.
4. `requireStrings(mixed)` gặp số `7` nên ném `IllegalArgumentException("non-string element")`; lời gọi trong `try/catch` in thông báo lỗi.
5. `refined(numbers)` nhận tham số kiểu tĩnh `List<Integer>` trỏ tới `ArrayList`. Mẫu `ArrayList<Integer> arrayList` hợp lệ theo quy tắc casting conversion; hai giá trị `2` và `3` được cộng thành `5`.

Đoạn chạy thể hiện **hai bài toán riêng**: **(a)** xác định kiểu collection và xác thực phần tử thật sự, **(b)** làm hẹp kiểu triển khai collection trong khi giữ type argument đã được biết tĩnh.

## 7. Pattern variable chỉ dùng khi chắc chắn match

Khi mẫu khớp, biến mới được khởi tạo và có phạm vi theo **flow scoping**.

**Ví dụ đúng với toán tử `&&`:**

~~~java
if (input instanceof List<?> list && !list.isEmpty()) {
    System.out.println("size=" + list.size());
}
~~~

Đây là đoạn code minh họa trong phạm vi có `Object input`. Do `&&` có short-circuit, vế phải chỉ được đánh giá nếu mẫu khớp; biến `list` khi ấy đã được khởi tạo.

**Ví dụ đúng với guard clause:**

~~~java
if (!(input instanceof List<?> list)) {
    throw new IllegalArgumentException("not a list");
}
System.out.println(list.size());
~~~

Dòng sau `if` chỉ có thể đạt tới khi mẫu khớp, vì nhánh thất bại đã `throw`.

**Ví dụ sai:**

~~~java
// CỐ Ý SAI: vế phải có thể chạy khi mẫu thất bại.
if (input instanceof List<?> list || list.isEmpty()) {
    System.out.println("checked");
}
~~~

Với `||`, vế phải có thể chạy khi vế trái `false`, lúc đó biến mẫu `list` chưa có giá trị được gán; vì vậy code không biên dịch.

Flow scoping là một quy tắc **an toàn biến**, **không phải** cách kiểm tra type arguments của generic. Biến `list` trong những ví dụ đúng có kiểu `List<?>`, vẫn không phải `List<String>`.

## 8. Những giới hạn quan trọng khác

### 8.1. Không thể dùng class literal cho kiểu generic có type argument

~~~java
// CỐ Ý SAI:
Class<?> c = List<String>.class;
~~~

`List<String>.class` không tồn tại trong cú pháp Java; `List.class` là class literal hợp lệ. Reflection có thể đọc khai báo kiểu generic ở class, field, parameter thông qua `Type`/`ParameterizedType`, nhưng điều đó **không biến** một đối tượng list runtime thành một instance mang nhãn `List<String>` có thể kiểm tra bằng `instanceof`.

### 8.2. Không dùng unchecked cast để thay một kiểm tra không có thật

~~~java
// Ví dụ nguy hiểm: cast tới List<String> có thể đưa ra
// cảnh báo unchecked và không kiểm tra từng phần tử.
@SuppressWarnings("unchecked")
static List<String> unsafe(Object input) {
    return (List<String>) input;
}
~~~

Nếu `input` là `List<Integer>`, phép cast trên có thể vượt qua bước kiểm tra class runtime do chỉ còn `List`, nhưng khi đọc phần tử và sử dụng như `String` có thể ném `ClassCastException`. `@SuppressWarnings("unchecked")` chỉ **ẩn cảnh báo**, không bổ sung kiểm tra an toàn.

**Lựa chọn thích hợp:** `List<?>` + kiểm tra từng phần tử + tạo một list kiểu cụ thể khi ứng dụng thật sự cần `List<String>`.

### 8.3. Kiểu generic ở vế trái không bảo vệ khỏi heap pollution

Java kiểm tra tính tương thích generic ở **compile time**. Nếu có raw type, unchecked conversion hoặc mã không tuân thủ hợp đồng kiểu, một biến khai báo `List<Integer>` vẫn có thể chứa giá trị không phải `Integer`. Mẫu `instanceof ArrayList<Integer> a` trong mục 5 chỉ xác nhận kiểu triển khai ở runtime; nó không tự phát hiện sự vi phạm nội dung này.

Vì vậy, trong code có dữ liệu không tin cậy hoặc bridge từ raw APIs, không thể dựa vào `instanceof ArrayList<Integer>` để chứng minh danh sách chứa toàn số nguyên hợp lệ. Nếu yêu cầu bảo đảm từng phần tử, hãy validate dữ liệu đầu vào.

### 8.4. Đối tượng null luôn không khớp với type pattern instanceof

~~~java
Object input = null;
boolean ok = input instanceof List<?> list;
System.out.println(ok); // false
~~~

Không có biến `list` được khởi tạo ở đường không khớp. Việc thử `input instanceof List<?>` không thay thế một chính sách null/empty input theo nghiệp vụ; quyết định cần từ chối hay chấp nhận `null` và báo lỗi phù hợp.

### 8.5. Không dùng type pattern để bỏ qua giới hạn variance

Dù `List<Integer>` và `List<Number>` đều là list và `Integer extends Number`, các kiểu generic này **không có quan hệ subtype** chỉ nhờ quan hệ giữa type arguments. Nếu cần đọc nhiều loại số, `List<? extends Number>` có thể là một kiểu tham số phù hợp cho API, nhưng từ một `Object` không thể chứng minh trực tiếp mẫu `List<? extends Number>` ở runtime. Kiểm tra từng phần tử vẫn là cách xác thực dữ liệu thực tế.

## 9. Checklist chọn cách giải quyết

| Nhu cầu | Cách phù hợp | Không nên làm |
|---|---|---|
| Chỉ cần biết một `Object` có phải danh sách hay không | `input instanceof List<?> list` | Dùng raw `List` không cần thiết |
| Cần đọc và xử lý mọi phần tử dưới dạng `Object` | Duyệt `List<?>` | Ép toàn list thành `List<String>` khi chưa kiểm tra |
| Cần chắc chắn từng phần tử là `String` | `element instanceof String s` trong vòng lặp, dựng `List<String>` mới | Dùng `Object instanceof List<String>` |
| Muốn làm hẹp `List<Integer>` thành `ArrayList<Integer>` | Mẫu `ArrayList<Integer> a` khi compiler cho phép | Tưởng rằng JVM xác nhận từng `Integer` |
| Xử lý dữ liệu JSON/ngoại vi chưa có kiểu tin cậy | Validate cấu trúc và nội dung với bộ chuyển đổi phù hợp | Dùng unchecked cast rồi tắt warning |
| Cần thông tin generic của một khai báo | Dùng API reflection về `Type`, hoặc cơ chế type token của thư viện nếu phù hợp | Nghĩ `List<String>.class` là runtime class hợp lệ |
| Muốn dùng pattern variable ở biểu thức điều kiện | Đảm bảo control flow đi qua nhánh đã match, thường với `&&` | Dùng biến mẫu ở vế phải `||` khi có thể chưa khởi tạo |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `Object value = List.of("a", "b");`. Vì sao `value instanceof List<String> names` không biên dịch?

**Đáp án:** Kiểu tĩnh bên trái chỉ là `Object`. Không có casting conversion kiểm tra được type argument `String` ở runtime; `List<String>` là kiểu không reifiable trong ngữ cảnh này. Hãy dùng `List<?> names` và kiểm tra phần tử nếu cần.

**Câu 2.** `value instanceof List<?> list` chứng minh các phần tử thuộc kiểu gì?

**Đáp án:** Không chứng minh kiểu phần tử cụ thể nào. Nó kiểm tra đối tượng là `List` và cho phép thao tác an toàn qua wildcard.

**Câu 3.** Vì sao `List<Integer> numbers; numbers instanceof ArrayList<Integer> arrayList` có thể hợp lệ trên Java 17 dù kiểu `ArrayList<Integer>` không reifiable?

**Đáp án:** Compiler đã biết `Integer` từ kiểu tĩnh `List<Integer>` và có casting conversion hợp lệ tới `ArrayList<Integer>`. Runtime kiểm tra kiểu triển khai `ArrayList`, **không** kiểm tra từng phần tử `Integer`. Đây là thay đổi hợp lệ từ Java 16+, không phải ngoại lệ khiến generic được reify.

**Câu 4.** Sau khi kiểm tra `List<?>`, có thể thực hiện `list.add("x")` không?

**Đáp án:** Không nên và thường không được compiler cho phép vì kiểu phần tử thực tế chưa rõ. Có thể gọi `list.size()` hoặc đọc phần tử dưới dạng `Object`; nếu cần list có thể thêm `String`, tạo một `List<String>` mới đã xác thực.

**Câu 5.** Nếu `requireStrings` nhận một list rỗng, nó có trả về được `List<String>` không?

**Đáp án:** Có. Không có phần tử trái yêu cầu, vòng lặp không lỗi và phương thức tạo một danh sách chuỗi rỗng. Đây là lựa chọn theo hợp đồng kiểm tra “mọi phần tử đều là chuỗi”; các ứng dụng muốn list không rỗng phải thêm điều kiện riêng.

**Câu 6.** Vì sao `if (value instanceof List<?> list || list.isEmpty())` sai?

**Đáp án:** Khi mẫu ở vế trái không khớp, Java mới đánh giá vế phải của `||`, trong khi `list` chưa được khởi tạo. Thay bằng `&&` cho phép dùng biến khi đã match, hoặc tách bước kiểm tra.

**Câu 7.** Ép `(List<String>) someObject` có kiểm tra từng phần tử để ngăn `ClassCastException` không?

**Đáp án:** Không. Generic cast từ dữ liệu chưa tin cậy có thể là *unchecked*; phần tử sai kiểu có thể gây `ClassCastException` về sau. Hãy xác thực nội dung khi thật sự cần đảm bảo kiểu.

## Tài liệu tham khảo

- [Java Language Specification 17, `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).
- [Java Language Specification 17, `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7).
- [Java Language Specification 17, `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): quy tắc tương thích ở compile time, giới hạn runtime và ví dụ `List<Integer> instanceof ArrayList<Integer>` hợp lệ từ Java 16.
- [Java Language Specification 17, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): type patterns và phạm vi biến mẫu.
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): ví dụ sử dụng và flow scoping.
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): tính năng chính thức từ Java 16.

**Ghi nhớ:** **`List<?>` kiểm tra được “đây là list”, không kiểm tra được “đây là list của String”.** Trên Java 16+, một số mẫu với kiểu generic non-reifiable vẫn có thể hợp lệ nhờ thông tin kiểu tĩnh của biểu thức bên trái; điều đó không thay đổi bản chất type erasure. Với dữ liệu runtime cần bảo đảm kiểu phần tử, luôn kiểm tra từng phần tử hoặc áp dụng bộ xác thực dữ liệu phù hợp.