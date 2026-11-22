# Sửa lỗi wildcard bằng phương thức bắt giữ trong Java Generics

## Mục tiêu học tập

Khi làm việc với một danh sách `List<?>`, Java cho phép đọc phần tử nhưng thường không cho đưa chính phần tử vừa đọc trở lại danh sách bằng lời gọi `set` hoặc `add` trực tiếp. Một thông báo dễ gặp là `incompatible types: Object cannot be converted to CAP#1`. Đây là tình huống thực hành tiêu biểu của **wildcard capture**: compiler biết dấu `?` đại diện cho một kiểu cụ thể nào đó, nhưng một biểu thức thông thường không thể tùy ý gán giá trị trở lại vị trí đòi hỏi đúng kiểu chưa biết ấy.

Bài này tập trung vào cách viết **phương thức helper generic** để bắt giữ cùng một kiểu trong một lần gọi, thực hiện phép toán an toàn và giữ giao diện công khai đơn giản.

Sau bài, bạn có thể:

- Đọc và lý giải `CAP#1`, `capture of ?` và giới hạn của thao tác ghi trên `List<?>`.
- Viết helper dạng `private static <T> void helper(List<T> list)` và gọi nó từ phương thức nhận `List<?>`.
- Thực hiện đổi chỗ, xoay và sao chép phần tử **trong cùng một collection** mà không dùng raw type hay unchecked cast.
- Phân biệt trường hợp **một wildcard được bắt giữ** với **hai wildcard độc lập** không có bằng chứng cùng kiểu.
- Quyết định khi nào dùng capture helper, `? extends T`, `? super T`, generic method có tên T, hoặc API thư viện như `Collections.swap`.

## 1. Vấn đề: vì sao `List<?>` không cho ghi lại phần tử?

Xét một danh sách với loại phần tử không biết trước:

```java
static void rotateWrong(java.util.List<?> values) {
    values.set(0, values.get(1)); // Không biên dịch.
}
```

Đây là **mã lỗi có chủ đích**. Nếu list chứa `String`, nhìn bằng mắt thì lấy một phần tử của chính list rồi ghi vào vị trí khác phải an toàn. Vấn đề nằm ở cách compiler kiểm tra kiểu của từng biểu thức.

- `List<?>` không đồng nghĩa `List<Object>`. Dấu `?` biểu diễn một kiểu phần tử cụ thể **chưa biết**.
- Đọc qua `values.get(1)` có thể được dùng dưới dạng `Object`, bởi mọi kiểu tham chiếu hợp lệ đều là subtype của Object.
- Ghi qua `values.set(0, ...)` lại đòi hỏi giá trị có **đúng kiểu phần tử chưa biết ấy**, chứ không chỉ là một Object.
- Phương thức bên ngoài không đặt được tên cho kiểu capture để giữ quan hệ từ giá trị đọc đến giá trị ghi.

Vì vậy compiler không chứng minh được biểu thức truyền cho `set` thuộc đúng capture type mà `set` yêu cầu. Với `javac --release 17`, một thông báo lỗi có dạng:

```text
error: incompatible types: Object cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Object from capture of ?
```

`CAP#1` là **tên chẩn đoán nội bộ compiler** dành cho kiểu chưa biết được tạo khi thực hiện *capture conversion*. Nó không phải tên class runtime, không phải kiểu bạn có thể khai báo bằng Java, và số `#1` không mang ý nghĩa thiết kế cố định.

### Wildcard không có nghĩa mọi phần tử đều là Object

Ví dụ:

```java
java.util.List<String> words = new java.util.ArrayList<>();
java.util.List<?> view = words;

// view.add("A");  // Không biên dịch: chưa biết kiểu phần tử.
// view.add(42);   // Không biên dịch.
// view.add(null); // Hợp lệ về hệ thống kiểu, nếu list hỗ trợ sửa và null.
Object value = view.isEmpty() ? null : view.get(0);
```

Hai tham chiếu cùng chỉ tới một đối tượng, nhưng `view` cố tình giấu kiểu phần tử. Compiler chặn việc thêm giá trị tùy ý để bảo vệ một danh sách có thể thực sự là `List<String>`, `List<Integer>` hay `List<MyType>`.

Một điểm cần giữ riêng: **kiểm tra kiểu và khả năng thay đổi collection là hai vấn đề khác nhau**. Dù một thao tác đúng kiểu, một `List.of(...)` không sửa được vẫn có thể ném `UnsupportedOperationException` khi `set`/`add`.

## 2. Capture conversion làm gì?

Khi phương thức khai báo tham số `List<?>`, compiler có thể diễn giải dấu `?` tạm thời thành một **kiểu capture duy nhất** đối với một biểu thức, ví dụ `CAP#1 extends Object`. Đó là cách compiler theo dõi một kiểu ẩn trong quá trình suy luận và kiểm tra generic.

Giả sử có:

```java
static void consume(java.util.List<?> values) {
    // Tại điểm dùng, có thể nhìn values như List<CAP#1>.
}
```

Dòng chú thích là sơ đồ ý niệm; `CAP#1` không phải cú pháp Java hợp lệ. Từ List có phần tử kiểu CAP#1, compiler cho phép chuyển kết quả đọc ra `Object`. Nhưng khi chỉ có một biểu thức ở kiểu `Object`, compiler không thể dùng nó như `CAP#1`.

Một phương thức generic có **tham số kiểu được đặt tên** sẽ giữ được quan hệ này:

```java
private static <T> void replaceFirstWithSecond(java.util.List<T> values) {
    if (values.size() >= 2) {
        T second = values.get(1);
        values.set(0, second);
    }
}
```

Ở đây:

- `List<T>.get(1)` trả về đúng `T`.
- `List<T>.set(0, T)` nhận lại đúng `T`.
- Suy luận kiểu gắn `T` với một capture của wildcard khi gọi helper.
- Không có cast không an toàn, không có raw type.

Từ bên ngoài có thể viết:

```java
static void replaceFirstWithSecond(java.util.List<?> values) {
    replaceFirstWithSecondCaptured(values);
}

private static <T> void replaceFirstWithSecondCaptured(
        java.util.List<T> values) {
    if (values.size() >= 2) {
        T second = values.get(1);
        values.set(0, second);
    }
}
```

Các phương thức trên là **mẫu khai báo đặt trong cùng một lớp**, tên helper cố ý khác tên public để trình bày. Compiler suy ra `T` bằng kiểu capture của list truyền vào. Phần thân helper chỉ thao tác với phần tử lấy từ **chính list ấy**, nên quan hệ kiểu được bảo toàn.

Không cần tự khai báo kiểu `CAP#1`, không cần cast và không cần biết trước list chứa `String` hay `Integer`.

## 3. Quy trình sửa từng bước

Giả sử bạn bắt đầu từ chức năng “đổi phần tử đầu và cuối của bất kỳ danh sách nào”:

**Bước 1 — Viết chữ ký công khai theo nhu cầu.**

```java
static void swapEnds(java.util.List<?> values) {
    // Chấp nhận List<String>, List<Integer>, List<MyType>, ...
}
```

`List<?>` hợp lý vì caller không cần truyền thêm hay nhận về một giá trị có kiểu T cụ thể.

**Bước 2 — Không cố thực hiện phép ghi khó suy luận trực tiếp.**

```java
// SAI, chỉ minh họa:
// Object first = values.get(0);
// values.set(0, values.get(values.size() - 1));
// values.set(values.size() - 1, first);
```

Biến `Object first` đã đánh mất quan hệ với kiểu phần tử chưa biết. Hai lời gọi `set` đều gặp khó khăn về capture.

**Bước 3 — Chuyển thao tác sang helper generic.**

```java
static void swapEnds(java.util.List<?> values) {
    if (values.size() < 2) {
        return;
    }
    swapCaptured(values, 0, values.size() - 1);
}

private static <T> void swapCaptured(
        java.util.List<T> values, int left, int right) {
    T first = values.get(left);
    values.set(left, values.get(right));
    values.set(right, first);
}
```

Hai phương thức trên là đoạn có thể đặt trong một class để biên dịch. Khi truyền `List<?>` cho `swapCaptured`, compiler thực hiện capture conversion và suy luận một `T` thống nhất cho toàn bộ thao tác bên trong helper.

**Bước 4 — Giữ helper ở phạm vi hẹp.** Nên để helper `private` nếu chỉ phục vụ phương thức công khai. Bề mặt API vẫn dễ đọc: caller chỉ thấy `swapEnds(List<?>)`.

**Bước 5 — Kiểm tra điều kiện runtime.** List rỗng/ít hơn hai phần tử nên bỏ qua; list không sửa được sẽ ném `UnsupportedOperationException`; chỉ số sai có thể ném `IndexOutOfBoundsException`. Capture helper **chỉ giải quyết kiểu generic**, không tự sửa các điều kiện runtime.

## 4. Ví dụ Java 17 hoàn chỉnh: swap, rotate, duplicate và PECS

Chương trình sau minh họa ba thao tác thay đổi dữ liệu **trong cùng một `List<?>`** bằng helper capture, rồi so sánh với sao chép từ một danh sách sang danh sách khác bằng `extends`/`super`.

**Tệp `WildcardCaptureLab.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class WildcardCaptureLab {
    static void swapEnds(List<?> values) {
        if (values.size() < 2) return;
        swapCaptured(values, 0, values.size() - 1);
    }

    private static <T> void swapCaptured(List<T> values, int left, int right) {
        T previous = values.get(left);
        values.set(left, values.get(right));
        values.set(right, previous);
    }

    static void rotateRight(List<?> values) {
        rotateRightCaptured(values);
    }

    private static <T> void rotateRightCaptured(List<T> values) {
        if (values.size() < 2) return;
        T last = values.get(values.size() - 1);
        for (int i = values.size() - 1; i > 0; i--) {
            values.set(i, values.get(i - 1));
        }
        values.set(0, last);
    }

    static void duplicateFirst(List<?> values) {
        duplicateFirstCaptured(values);
    }

    private static <T> void duplicateFirstCaptured(List<T> values) {
        if (!values.isEmpty()) values.add(values.get(0));
    }

    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        destination.addAll(source);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        List<?> view = words;
        swapEnds(view);
        System.out.println("swap=" + words);
        rotateRight(view);
        System.out.println("rotate=" + words);
        duplicateFirst(view);
        System.out.println("duplicate=" + words);

        List<Integer> integers = new ArrayList<>(List.of(1, 2));
        List<Number> numbers = new ArrayList<>(List.of(0.5));
        appendAll(numbers, integers);
        System.out.println("append=" + numbers);

        List<?> fixed = List.of("x", "y");
        try {
            swapEnds(fixed);
        } catch (UnsupportedOperationException exception) {
            System.out.println("immutable=" + exception.getClass().getSimpleName());
        }

        Collections.swap(words, 0, 1);
        System.out.println("library=" + words);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all WildcardCaptureLab.java
java WildcardCaptureLab
```

**Stdout chính xác đã được kiểm chứng:**

```text
swap=[C, B, A]
rotate=[A, C, B]
duplicate=[A, C, B, A]
append=[0.5, 1, 2]
immutable=UnsupportedOperationException
library=[C, A, B, A]
```

Chương trình biên dịch bằng `javac --release 17 -Xlint:all` mà không phát sinh warning trong ví dụ đã kiểm tra. Các helper generic thực hiện thao tác có quan hệ kiểu rõ ràng.

### 4.1. `swapEnds` giữ đúng kiểu phần tử

Với `List<String>`, sau lời gọi `swapEnds(view)`, hai phần tử đầu và cuối đổi chỗ: `[A, B, C]` trở thành `[C, B, A]`.

Với `List<Integer>` cũng vậy: helper có thể nhận một capture khác và suy luận `T` tương ứng trong **lần gọi khác**. Không có chuyện helper lưu một “T toàn cục” bị cố định thành String sau lần gọi đầu tiên.

### 4.2. `rotateRight` cần giữ nhiều lần đọc/ghi cùng T

Trong `rotateRightCaptured`:

- `T last = values.get(size - 1)` giữ phần tử cuối dưới đúng kiểu `T`.
- Vòng lặp lần lượt di chuyển phần tử tại `i - 1` sang `i`.
- `values.set(0, last)` chuyển phần tử cuối về đầu.

Sau khi swap có `[C, B, A]`, xoay phải tạo `[A, C, B]`. Nếu list có ít hơn hai phần tử, phương thức giữ nguyên nội dung và tránh truy cập chỉ số ngoài phạm vi.

Cơ chế quan trọng không nằm ở thuật toán xoay, mà là mọi phép đọc/ghi nội bộ đều dùng **một T nhất quán**.

### 4.3. `duplicateFirst` có thể thêm phần tử đọc từ cùng list

Với `List<?>`, `view.add(view.get(0))` không biên dịch. Nhưng trong helper:

```java
private static <T> void duplicateFirstCaptured(List<T> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
```

kiểu `T` của phần tử đọc là đúng kiểu mà `add(T)` yêu cầu. Do đó có thể nhân đôi phần tử đầu: `[A, C, B]` thành `[A, C, B, A]`.

Điều này **không cho phép thêm một Object tùy ý**; giá trị phải là T, ở đây được lấy trực tiếp từ list đang được bắt giữ.

### 4.4. `appendAll` dùng PECS giữa hai danh sách có quan hệ kiểu

Trong `appendAll`, nguồn có kiểu `List<? extends T>` nên có thể **đọc T** từ danh sách nguồn. Đích có kiểu `List<? super T>` nên có thể **ghi T** vào danh sách đích.

Vì `Integer extends Number`, có thể truyền `List<Integer>` làm nguồn và `List<Number>` làm đích. Khi đó số `1` và `2` được thêm sau số `0.5`, tạo `[0.5, 1, 2]`.

Điểm khác với capture của một `List<?>` là **quan hệ giữa hai container**: API phải bảo đảm phần tử từ nguồn có thể được thêm an toàn vào đích. `extends`/`super` mô tả trực tiếp quan hệ ấy, trong khi hai wildcard `?` độc lập không tự biểu đạt nó.

### 4.5. Capture không làm collection bất biến trở nên sửa được

`List.of("x", "y")` là danh sách không sửa được. `swapEnds(fixed)` vẫn suy luận kiểu T thành công ở compile time; nhưng tại runtime `set` thất bại và ném `UnsupportedOperationException`.

Đây không phải lỗi capture. Generic type safety và mutability là hai vấn đề tách biệt. Phương thức có thể yêu cầu caller cung cấp danh sách sửa được theo hợp đồng, hoặc tạo một bản sao:

```java
List<String> copy = new ArrayList<>(List.of("x", "y"));
swapEnds(copy);
```

Đoạn ngắn này nằm trong ngữ cảnh đã import `List`/`ArrayList` và có phương thức `swapEnds`.

### 4.6. Thư viện sẵn có có thể thay helper tự viết

`Collections.swap(List<?> list, int i, int j)` đã hỗ trợ wildcard cho thao tác đổi chỗ. Nếu bài toán chỉ là swap, có thể gọi API này thay vì tự duy trì helper riêng.

Tương tự, `Collections.reverse(List<?>)` đảo danh sách mà không yêu cầu caller biết kiểu phần tử. Trước khi tạo capture helper phức tạp, hãy kiểm tra liệu thư viện chuẩn đã có phương thức thực hiện đúng thao tác hay chưa.

## 5. Ví dụ sai: lỗi `CAP#1` và cách đọc

**Tệp `InvalidCapture.java` — cố ý không biên dịch:**

```java
import java.util.List;

class InvalidCapture {
    static void rotate(List<?> values) {
        values.set(0, values.get(1));
    }

    static void move(List<?> source, List<?> target) {
        target.add(source.get(0));
    }
}
```

Lệnh thử:

```bash
javac --release 17 InvalidCapture.java
```

`javac` từ chối hai câu lệnh. Phần thông báo cốt lõi (đã kiểm chứng):

```text
error: incompatible types: Object cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Object from capture of ?
```

Thông báo tương tự xuất hiện ở hai vị trí nhưng **ý nghĩa cần phân tích khác nhau**:

- `values.set(0, values.get(1))`: phần tử lấy từ **chính cùng list**; về bản chất có thể an toàn. Đây là ứng viên tốt để dùng helper capture với một T.
- `target.add(source.get(0))`: phần tử từ **source** được đưa vào một **target độc lập**, cả hai chỉ có kiểu `List<?>`. Không có bằng chứng chúng chứa cùng loại phần tử. Việc viết một helper một T không thể tự hợp thức hóa phép chuyển này.

Vì vậy, không nên hiểu mọi lỗi `CAP#1` đều sửa được bằng cùng một thao tác mà không thay đổi hợp đồng. Hãy hỏi: **Hai vị trí đọc/ghi có thực sự thuộc cùng một kiểu?** Nếu có, capture helper giúp trình biên dịch diễn đạt được điều đó. Nếu không, phải bổ sung thông tin kiểu hoặc kiểm tra thực tế.

## 6. Hai wildcard độc lập là hai capture riêng

Xét đoạn minh họa:

```java
static void move(List<?> source, List<?> destination) {
    moveCaptured(source, destination);
}

private static <T> void moveCaptured(
        List<T> source, List<T> destination) {
    if (!source.isEmpty()) {
        destination.add(source.get(0));
    }
}
```

Đoạn này **không biên dịch** khi gọi `moveCaptured` bằng hai `List<?>` độc lập. Với `javac --release 17`, lỗi suy luận có dạng:

```text
required: List<T>,List<T>
found:    List<CAP#1>,List<CAP#2>
reason: inference variable T has incompatible equality constraints CAP#2,CAP#1
```

Giải thích:

- `source` có một kiểu phần tử chưa biết, tạm gọi `CAP#1`.
- `destination` có một kiểu phần tử chưa biết độc lập, tạm gọi `CAP#2`.
- Việc cả hai cùng viết `List<?>` không chứng minh `CAP#1` bằng `CAP#2`.
- Helper yêu cầu **cùng T**, nên lời gọi không được chấp nhận.

Ví dụ runtime hoàn toàn có thể là `source = List<String>` và `destination = List<Integer>`. Nếu compiler cho sao chép tùy ý, dữ liệu của đích sẽ bị trộn sai kiểu.

Điểm tinh tế: ngay cả nếu bạn *biết* hai tham chiếu tình cờ trỏ vào cùng một loại danh sách trong một tình huống cụ thể, chữ ký `move(List<?>, List<?>)` vẫn không diễn đạt quan hệ giữa chúng. Java kiểm tra theo hợp đồng kiểu có thể chứng minh tại compile time, không chấp nhận một suy đoán dựa trên dữ liệu mẫu.

### Ba cách thiết kế đúng cho hai collection

**Cách 1 — Caller biết cùng một T:**

```java
static <T> void moveSameType(List<T> source, List<T> target) {
    if (!source.isEmpty()) {
        target.add(source.get(0));
    }
}
```

Phương thức nên nằm trong một lớp có import `java.util.List`. Caller truyền hai danh sách thực sự có cùng kiểu T.

**Cách 2 — Quan hệ subtype/supertype (PECS):**

```java
static <T> void copyInto(
        List<? extends T> source,
        List<? super T> target) {
    target.addAll(source);
}
```

Mẫu này cho phép chuyển phần tử từ `List<Integer>` sang `List<Number>`, hoặc từ `List<String>` sang `List<Object>`. API đặt ra quan hệ kiểu cần thiết.

**Cách 3 — Dữ liệu không rõ kiểu từ nguồn ngoài:** Nhận `List<?>` và một token `Class<T>` để xác thực từng phần tử trước khi thêm vào `List<T>`.

```java
static <T> void appendValidated(
        List<?> source, List<T> target, Class<T> type) {
    for (Object value : source) {
        target.add(type.cast(value));
    }
}
```

Phương thức này có thể thay đổi target một phần nếu dữ liệu lỗi xuất hiện giữa quá trình. Nếu cần **all-or-nothing**, trước tiên kiểm tra và sao chép vào một danh sách tạm typed rồi mới `target.addAll(validated)`. Class token chỉ kiểm tra các kiểu runtime biểu diễn được, như `String.class`; với phần tử generic lồng nhau cần xác thực sâu hơn.

## 7. Chọn wildcard hay type variable cho API?

Một nguyên tắc thường hữu ích: **dùng wildcard khi kiểu cụ thể không liên quan tới hợp đồng công khai**, còn **dùng type variable có tên khi cần diễn đạt quan hệ giữa nhiều vị trí**.

So sánh:

| Ý định | Chữ ký thích hợp | Vì sao |
| --- | --- | --- |
| Chỉ xem số phần tử | `int size(List<?> values)` | Không cần tên T. |
| Duyệt và in bất kỳ phần tử nào | `void print(List<?> values)` | Đọc dưới dạng Object là đủ. |
| Đổi vị trí phần tử trong cùng một danh sách | `void swap(List<?> values, ...)` cùng helper `<T>` | Public API đơn giản; helper giữ quan hệ đọc/ghi. |
| Trả về chính phần tử đầu dưới kiểu caller biết | `<T> T first(List<T> values)` | T liên hệ kiểu phần tử với kiểu trả về. |
| Sao chép nguồn vào đích có kiểu rộng hơn | `<T> void copy(List<? extends T>, List<? super T>)` | Hai collection có quan hệ kiểu rõ ràng. |
| Thêm Integer vào một sink có thể chứa Number/Object | `void addInt(List<? super Integer> sink)` | Đích nhận Integer, không cần capture helper. |
| Đọc Number từ danh sách các subtype của Number | `void consume(List<? extends Number> source)` | Đọc Number an toàn; không ghi Number tùy ý. |

Nếu bạn có:

```java
static <T> void printAny(List<T> values) {
    for (T element : values) {
        System.out.println(element);
    }
}
```

mà T chỉ xuất hiện một lần trong chữ ký và không cần quan hệ khác, thường có thể đơn giản hóa thành `printAny(List<?> values)`. Tuy nhiên, **không phải cứ T xuất hiện một lần là luôn thừa**: hãy xét toàn bộ thân hàm, overload resolution và kiểu trả về. Khi T cần thiết để giữ dữ liệu qua nhiều thao tác, generic helper vẫn có giá trị.

## 8. Wildcard với bound `extends` và `super`

Capture helper không giới hạn ở wildcard không bound.

### 8.1. `? extends Number`

Nếu hàm nhận `List<? extends Number>`, phần tử đọc được dưới dạng Number:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Đây là phương thức minh họa bên trong lớp, với import `List`. Vì không cần ghi, **không cần helper**.

Nếu nhiệm vụ là lấy một phần tử từ danh sách và thêm lại vào **chính danh sách đó**, có thể viết:

```java
static void duplicateNumber(List<? extends Number> values) {
    duplicateNumberCaptured(values);
}

private static <T extends Number> void duplicateNumberCaptured(
        List<T> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
```

Chữ ký helper giữ được T trong giới hạn Number; compiler có thể bắt giữ kiểu phần tử thực từ wildcard extends Number. Việc thêm một `Number` bất kỳ vào List có phần tử chưa biết (có thể là Integer) vẫn không được phép.

### 8.2. `? super Integer`

Một danh sách `List<? super Integer>` là **consumer** có thể nhận Integer:

```java
static void addInteger(List<? super Integer> destination) {
    destination.add(10);
}
```

Chữ ký này thích hợp khi caller truyền `List<Integer>`, `List<Number>` hoặc `List<Object>`. Khi đọc từ một danh sách `List<? super Integer>`, không thể tự suy ra kết quả là Integer; kiểu có thể đọc an toàn nói chung là Object.

Bạn không cần capture helper để thêm Integer vì bound `super Integer` đã bảo đảm phép ghi.

### 8.3. Capture helper không thay thế nguyên tắc PECS

**Producer Extends, Consumer Super** là cách nghĩ hữu ích khi API có một phía tạo/đọc phần tử và một phía nhận/ghi phần tử. Capture helper xử lý tình huống khác: **cùng một container có kiểu chưa biết nhưng cần thao tác nội bộ nhất quán**.

Không nên bắt mọi API về `List<?>` rồi cố dùng helper phức tạp. Nếu biết rõ loại phần tử cần ghi từ bên ngoài, hãy biểu đạt trực tiếp bằng `List<T>` hoặc `List<? super T>`.

## 9. Quyết định dùng Collections API hay tự viết helper capture

Trước khi tự viết helper `<T>`, hãy hỏi **thao tác mong muốn đã có trong thư viện chuẩn chưa**. Những phương thức dưới đây nhận một list với element type bất kỳ và thực hiện thay đổi vị trí các giá trị *đã có*, không cần caller đoán element type:

| Ý định | API sẵn có | Rủi ro cần xem xét |
|---|---|---|
| Đổi chỗ hai phần tử | `Collections.swap(List<?>, i, j)` | Chỉ số hợp lệ, list hỗ trợ `set` |
| Đảo thứ tự | `Collections.reverse(List<?>)` | List có cho sửa không |
| Xoay theo khoảng cách | `Collections.rotate(List<?>, distance)` | Có thể thay toàn bộ vị trí |
| Xáo trộn | `Collections.shuffle(List<?>)` | Kết quả ngẫu nhiên, không hứa một stdout cố định |

Ví dụ đặt trong method với `import java.util.*`:

```java
List<?> letters = new ArrayList<>(List.of("A", "B", "C"));
Collections.rotate(letters, 1);
System.out.println(letters); // [C, A, B]
```

`List<?>` không cho thêm một `String` tùy ý qua tham chiếu `letters`, nhưng **không cấm API hợp lệ hoán chuyển các phần tử trong cùng list**. Quan hệ kiểu được bảo toàn vì thao tác chỉ thay vị trí những giá trị vốn thuộc chính list đó.

Nếu thuật toán cần giữ một phần tử qua nhiều lần `get`/`set`, không có sẵn trong thư viện, wrapper `List<?>` kết hợp helper `<T> void operation(List<T>)` là lựa chọn rõ ràng. Nếu cần chuyển dữ liệu **giữa hai collections có element types khác nhau**, cần xác định quan hệ PECS, không giả định hai capture `?` độc lập tương thích.

Chú ý: `Collections.sort` còn yêu cầu yếu tố so sánh thích hợp, **không phải** thao tác có thể áp dụng cho mọi `List<?>` giống `reverse`. Các thao tác thay đổi list vẫn có thể ném `UnsupportedOperationException` nếu caller đưa `List.of(...)`; capture conversion không thay thế hợp đồng mutability.

## 10. Lỗi hay gặp khi sửa `capture of ?`

| Cách sửa sai hoặc thiếu | Vấn đề | Cách sửa tốt hơn |
| --- | --- | --- |
| Đổi `List<?>` thành raw `List` | Mất kiểm tra generic, có thể đưa sai kiểu vào danh sách. | Dùng helper `<T>` hoặc điều chỉnh hợp đồng với PECS. |
| Ép `(List<Object>) values` | Cast generic không chứng minh loại phần tử, có thể là unchecked và làm hỏng dữ liệu. | Giữ capture bằng `List<T>` trong helper. |
| Dùng `Object` để tạm giữ phần tử rồi `set` | `Object` có thể rộng hơn kiểu capture cần nhận. | Biến cục bộ `T first` trong helper generic. |
| Gọi helper với hai `List<?>` bất kỳ | Hai wildcard tạo hai capture riêng, không chứng minh cùng T. | Dùng `<T>` ở chữ ký caller hoặc `extends/super`. |
| Cho rằng capture helper khiến `List.of` sửa được | Generic typing không thay đổi mutability của object. | Truyền list mutable hoặc tạo bản sao. |
| Suy ra `?` luôn là Object | Wildcard đại diện kiểu chưa biết; Object chỉ là kiểu đọc an toàn phổ biến. | Giữ sự khác biệt giữa đọc Object và ghi capture. |
| Cho rằng `CAP#1` là một class thật | Nó là tên compiler dùng khi báo lỗi suy luận. | Đọc ràng buộc capture, xác định các vị trí liên quan. |
| Suppress warning thay vì thay đổi chữ ký | Che dấu rủi ro type safety, không thiết lập quan hệ kiểu. | Thiết kế lại API và kiểm chứng bằng compile. |
| Tạo helper quá công khai | Bề mặt API lộ chi tiết kỹ thuật không cần thiết. | Giữ helper private nếu chỉ dùng nội bộ. |

### Cảnh báo về ép kiểu

Không nên sửa bằng một đoạn có raw cast như:

```java
// KHÔNG NÊN DÙNG:
@SuppressWarnings({"unchecked", "rawtypes"})
static void unsafeRotate(List<?> values) {
    List raw = values;
    raw.set(0, raw.get(1));
}
```

Đoạn này có thể biên dịch, nhưng dùng raw type để loại bỏ kiểm tra kiểu. Dù thao tác cụ thể đang lấy và ghi phần tử trong cùng danh sách, API không còn cơ chế compile-time buộc bạn chỉ ghi giá trị tương thích ở những thay đổi tiếp theo. Helper generic làm rõ bất biến: đầu vào và đầu ra nội bộ đều là T.

## 11. Thực hành với compile error và kiểm chứng

Khi gặp thông báo:

```text
incompatible types: Object cannot be converted to CAP#1
```

hãy làm theo trình tự:

1. **Xem câu lệnh đang ghi vào đâu:** `List<?>.add`, `List<?>.set` hoặc phương thức khác nhận tham số capture.
2. **Xác định đối tượng được lấy từ đâu:** cùng list, list khác hay nguồn dữ liệu bất kỳ.
3. **Nếu cùng list**, thử đặt thao tác trong helper `<T> void helper(List<T> values)`; chuyển cả logic đọc và ghi vào cùng helper.
4. **Nếu khác list**, đừng dùng một T tùy ý chỉ để compiler hết lỗi. Hãy bổ sung quan hệ kiểu: `List<T>` ở cả hai phía, hoặc `<? extends T>`/`<? super T>`.
5. **Chạy `javac` trước** khi viết thêm cast. Nếu helper đúng, nó thường không cần `@SuppressWarnings("unchecked")`.
6. **Chạy thử với nhiều loại phần tử** và với collection không sửa được để phân biệt compile-time type safety với runtime mutability.
7. **Kiểm tra empty list và chỉ số** để tránh `IndexOutOfBoundsException`, đồng thời xác định ý nghĩa của việc thêm phần tử, đổi thứ tự và alias.

Ví dụ test thủ công đáng thực hiện:

```java
// Đặt trong main của một lớp đã định nghĩa swapEnds.
List<Integer> ints = new ArrayList<>(List.of(10, 20, 30));
swapEnds(ints);
System.out.println(ints); // [30, 20, 10]
```

Để tự biên dịch đoạn này độc lập, cần class chứa `swapEnds` cùng import `List`/`ArrayList`. Nếu đã chạy chương trình phần 4, bạn có thể thêm đoạn này vào `main` và kiểm tra đầu ra mới.

### Khi nào không cần helper?

Nếu yêu cầu chỉ đọc:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

thì không cần capture helper. Nếu chỉ thêm đối tượng được biết trước là Integer vào consumer:

```java
static void addTen(List<? super Integer> destination) {
    destination.add(10);
}
```

cũng không cần. Chỉ tạo helper khi nó giải quyết **một quan hệ kiểu bị wildcard che đi mà compiler chưa thể duy trì qua các biểu thức**.

## 12. Bài tập tự kiểm tra

**Bài 1.** Vì sao `List<?> list` cho phép `list.get(0)` nhưng từ chối `list.set(0, list.get(1))`?

**Đáp án:** Lúc đọc, có thể nhìn phần tử dưới dạng Object; lúc ghi, `set` cần kiểu capture chưa biết. Một biểu thức đọc được sử dụng dưới dạng Object không bảo đảm tương thích với capture trong chữ ký kiểm tra trực tiếp. Helper generic có tên T giúp biểu đạt quan hệ cùng kiểu.

**Bài 2.** Viết chữ ký helper cho phép chuyển phần tử cuối lên đầu trong cùng một list bất kỳ.

**Đáp án:**

```java
static void rotateRight(List<?> values) {
    rotateRightCaptured(values);
}

private static <T> void rotateRightCaptured(List<T> values) {
    if (values.size() < 2) return;
    T last = values.get(values.size() - 1);
    for (int i = values.size() - 1; i > 0; i--) {
        values.set(i, values.get(i - 1));
    }
    values.set(0, last);
}
```

Hai phương thức này là đoạn mã đặt trong một class đã import `List`.

**Bài 3.** Vì sao không được viết `copy(List<?> from, List<?> to) { to.add(from.get(0)); }`?

**Đáp án:** Kiểu phần tử của from và to chưa biết và có thể khác nhau. Không có bằng chứng rằng giá trị từ from tương thích kiểu phần tử mà to nhận.

**Bài 4.** Nếu muốn sao chép từ `List<Integer>` vào `List<Number>`, chữ ký nào phù hợp?

**Đáp án:** `<T> void appendAll(List<? super T> destination, List<? extends T> source)`; trình biên dịch có thể chọn T phù hợp để cho phép đọc từ source và ghi vào destination.

**Bài 5.** Helper generic có giải quyết `UnsupportedOperationException` khi `set` trên `List.of` không?

**Đáp án:** Không. Helper chỉ hỗ trợ kiểm tra generic. List không sửa được vẫn từ chối `set` hoặc `add`.

**Bài 6.** Tại sao thay `List<?>` bằng raw `List` làm biến mất lỗi compiler nhưng vẫn là lựa chọn kém?

**Đáp án:** Raw List bỏ ràng buộc phần tử, có thể cho ghi đối tượng không tương thích. Nó không chứng minh quan hệ kiểu; về sau dễ dẫn tới heap pollution và `ClassCastException`.

**Bài 7.** Một helper `<T> void change(List<T> values)` chỉ được gọi từ `List<?>` chứa String. Có phải T luôn là String trong mọi lần gọi tương lai không?

**Đáp án:** Không. T được suy luận độc lập cho mỗi lời gọi. Một lần khác, helper có thể nhận list chứa Integer, Number hoặc một lớp tự định nghĩa.

**Bài 8.** Có nên tạo helper chỉ để gọi `Collections.swap` không?

**Đáp án:** Thường không; `Collections.swap` đã nhận `List<?>` và hỗ trợ trực tiếp thao tác đổi chỗ. Dùng helper riêng khi thuật toán cần nhiều phép đọc/ghi liên kết hoặc thư viện không có phương thức đáp ứng yêu cầu.

## 13. Ghi nhớ

- `List<?>` chứa một loại phần tử **chưa biết**, không phải `List<Object>`.
- Compiler có thể gán một tên tạm như `CAP#1` cho kiểu capture; tên này chỉ phục vụ suy luận và chẩn đoán.
- Nếu thao tác **đọc và ghi cùng một danh sách**, phương thức helper `<T> void helper(List<T> list)` thường giữ được quan hệ an toàn giữa các phần tử của danh sách.
- Nếu thao tác chuyển phần tử **giữa hai danh sách độc lập**, hai `?` không tự bảo đảm cùng kiểu. Hãy dùng generic signature thể hiện quan hệ hoặc PECS.
- Capture helper không thay đổi việc list có sửa được hay không, không thay đổi runtime erasure và không phải lý do để thêm unchecked cast.
- Ưu tiên API công khai ngắn gọn và các tiện ích thư viện chuẩn; giữ logic capture trong helper private khi chỉ phục vụ triển khai.

Khi đọc lỗi `capture of ?`, câu hỏi đúng không phải “làm sao ép compiler chấp nhận Object?”, mà là **giá trị được ghi có được chứng minh thuộc cùng kiểu chưa biết mà container yêu cầu hay không?** Nếu câu trả lời là có vì nó đến từ cùng container, một helper generic có tên T là cách diễn đạt quan hệ đó một cách rõ ràng, an toàn và dễ bảo trì.
