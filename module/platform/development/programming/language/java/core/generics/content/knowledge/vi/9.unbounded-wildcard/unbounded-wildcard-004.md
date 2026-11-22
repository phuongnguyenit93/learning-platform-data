# Giới hạn thêm và thay phần tử qua `List<?>` trong Java

## 1. Vấn đề cần hiểu

Trong Java, `List<?>` là một `List` có **kiểu phần tử chưa biết**. Ký hiệu `?` là *unbounded wildcard* (wildcard không giới hạn). Nó cho phép tham chiếu tới danh sách có nhiều kiểu phần tử khác nhau mà không đánh mất kiểm tra kiểu của generics:

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

List<?> first = words;    // Hợp lệ
List<?> second = numbers; // Hợp lệ
```

Tuy nhiên, việc có thể tham chiếu tới `List<String>` hoặc `List<Integer>` không có nghĩa có thể thêm bất kỳ giá trị nào vào danh sách thông qua biến `List<?>`.

Nguyên tắc trung tâm:

- **Đọc:** phần tử lấy ra có thể được dùng an toàn dưới kiểu `Object`.
- **Thêm hoặc thay bằng giá trị khác `null`:** trình biên dịch không biết giá trị có đúng kiểu phần tử thực tế hay không, nên không cho phép.
- **Thêm/thay bằng `null`:** có thể **biên dịch**, bởi `null` tương thích với mọi kiểu tham chiếu; việc thực thi vẫn có thể thất bại tùy danh sách.
- **Xóa, làm rỗng hoặc thay đổi vị trí phần tử:** nhiều thao tác vẫn có thể biên dịch vì không phải đưa một giá trị mới không rõ kiểu vào danh sách.

`List<?>` **không đồng nghĩa với danh sách bất biến hoặc chỉ đọc** (*immutable/read-only list*). Giới hạn kiểu ở lúc biên dịch và khả năng sửa đổi của đối tượng danh sách tại lúc chạy là hai vấn đề khác nhau.

## 2. Vì sao không thể `add` một phần tử cụ thể?

Xét ví dụ:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;

unknown.add("Java"); // LỖI BIÊN DỊCH
unknown.add(10);     // LỖI BIÊN DỊCH
unknown.add(new Object()); // LỖI BIÊN DỊCH
```

Trình biên dịch biết `unknown` tham chiếu đến danh sách có một kiểu phần tử nào đó, nhưng **không thể giả định kiểu đó là `String`, `Integer` hay `Object`**. Nếu `add(10)` được phép qua `List<?>` đang trỏ vào `List<String>`, một giá trị `Integer` sẽ lọt vào danh sách vốn được cam kết chứa `String`.

Về khái niệm, trình biên dịch tạo một kiểu nội bộ thường được gọi là **wildcard capture**, chẳng hạn `CAP#1`, để đại diện cho kiểu phần tử chưa biết trong một ngữ cảnh sử dụng `List<?>`. `add(E)` cần đối số thuộc đúng kiểu `E`, trong khi `String` hay `Integer` không được bảo đảm tương thích với `CAP#1`.

Lỗi này không liên quan đến việc danh sách có đang trống hay không:

```java
List<?> empty = new ArrayList<String>();
empty.add("hello"); // Vẫn là lỗi biên dịch
```

Biểu thức `new ArrayList<String>()` ở vế phải không khiến tham số `?` của **biến** `empty` trở thành `String` trong các lời gọi tiếp theo.

Đồng thời, `List<?>` **không phải** `List<Object>`:

```java
List<String> strings = new ArrayList<>();
List<Object> objects = strings; // LỖI BIÊN DỊCH
List<?> unknown = strings;     // Hợp lệ
```

`List<Object>` có thể nhận đối tượng `Object` bất kỳ qua `add`; `List<?>` không cho phép thao tác đó.

## 3. Ngoại lệ về kiểu: có thể thêm `null`

`null` là giá trị tham chiếu đặc biệt, tương thích với mọi kiểu tham chiếu, kể cả kiểu phần tử chưa biết do wildcard capture biểu diễn. Vì vậy:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;

unknown.add(null); // BIÊN DỊCH ĐƯỢC; ArrayList cho phép null
System.out.println(strings); // [null]
```

Chú ý chính xác sự khác biệt giữa **được trình biên dịch chấp nhận** và **thao tác thành công lúc chạy**:

```java
List<?> unmodifiable = List.of("Java");
unmodifiable.add(null); // Biên dịch được; ném UnsupportedOperationException
```

`List.of(...)` tạo danh sách không hỗ trợ các thao tác sửa đổi. Do đó, mặc dù `null` được phép ở mức kiểu, phương thức `add` vẫn ném `UnsupportedOperationException`. Một triển khai danh sách tự viết cũng có thể từ chối `null` theo hợp đồng riêng.

**Không nên** coi `add(null)` là cách hữu ích để vượt qua wildcard. Nó không cho phép thêm dữ liệu nghiệp vụ có kiểu cụ thể và có thể tạo phần tử `null` không mong muốn.

## 4. Giới hạn của `set(index, value)`

Phương thức `set(int index, E element)` thay phần tử tại vị trí có sẵn. Nó không thay đổi kích thước danh sách, nhưng vẫn đưa **một giá trị mới** vào vị trí phải giữ đúng kiểu phần tử `E`. Vì vậy quy tắc wildcard vẫn áp dụng.

```java
List<?> unknown = new ArrayList<String>(List.of("A", "B"));

unknown.set(0, "C"); // LỖI BIÊN DỊCH
unknown.set(0, 99);  // LỖI BIÊN DỊCH
unknown.set(0, null); // BIÊN DỊCH ĐƯỢC
```

Nếu danh sách thực tế hỗ trợ `set` và cho phép `null`, phép thay thế cuối hoạt động:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<?> unknown = source;

Object previous = unknown.set(0, null);
System.out.println(previous); // A
System.out.println(source);   // [null, B]
```

`set` trả về phần tử cũ. Qua `List<?>`, ta có thể nhận giá trị đó dưới kiểu `Object`, vì mọi kiểu phần tử tham chiếu của generic đều là kiểu con của `Object`.

`set(index, null)` vẫn có thể thất bại do:

- **`IndexOutOfBoundsException`** nếu chỉ số ngoài phạm vi hợp lệ.
- **`UnsupportedOperationException`** nếu danh sách không hỗ trợ `set` (ví dụ danh sách trả về bởi `List.of`).
- **`NullPointerException` hoặc lỗi khác** nếu một triển khai có hợp đồng cấm `null` hoặc kiểm tra ràng buộc đặc thù.

Không được suy từ khai báo `List<?>` rằng danh sách chắc chắn sửa được.

### 4.1. Vì sao `list.set(0, list.get(0))` cũng có thể lỗi biên dịch?

Một trường hợp dễ gây ngạc nhiên:

```java
static void replaceWithItself(List<?> list) {
    list.set(0, list.get(0)); // LỖI BIÊN DỊCH
}
```

Lời gọi `get(0)` đọc được một phần tử. Nhưng ở biểu thức trên, Java không bảo đảm trình biên dịch sử dụng **cùng một kiểu capture** cho giá trị trả về của `get` và kiểu tham số cần thiết của `set`; kết quả `get` có thể được nhìn như một kiểu capture khác, nên không gán được cho tham số của `set`. Việc người lập trình biết hai thao tác dùng cùng đối tượng danh sách không đủ để cú pháp trên được chấp nhận.

Nếu cần đọc rồi ghi lại phần tử với cùng một kiểu chưa biết, hãy dùng **phương thức helper generic** để bắt giữ kiểu đó một lần:

```java
static <T> void replaceWithItselfCaptured(List<T> list) {
    if (!list.isEmpty()) {
        list.set(0, list.get(0)); // Hợp lệ: cả hai cùng T
    }
}

static void caller(List<?> values) {
    replaceWithItselfCaptured(values); // Wildcard capture khi gọi
}
```

Đây là thao tác thay bằng chính giá trị cũ nhằm minh họa kỹ thuật capture; nó không làm thay đổi dữ liệu. Phương thức helper vẫn có thể ném `UnsupportedOperationException` nếu danh sách thực tế không cho phép `set`.

## 5. Xóa hoặc hoán đổi là nhóm thao tác khác với đưa phần tử mới vào

`add(E)` và `set(int,E)` cần **giá trị thuộc kiểu phần tử E**. Còn `remove(int)`, `remove(Object)`, `clear()` chỉ bỏ dữ liệu hiện có nên không cần caller cung cấp một E mới. `Collections.swap(List<?>,i,j)` cũng hợp lệ vì thư viện dùng generic helper để bảo toàn cùng kiểu phần tử khi hoán đổi.

| Lời gọi qua `List<?>` | Biên dịch? | Lưu ý |
| --- | --- | --- |
| `get(0)`, `size()` | Có | `get` cần chỉ số hợp lệ. |
| `add("A")`, `set(0,"A")` | Không | String chưa chắc là kiểu của wildcard. |
| `add(null)`, `set(0,null)` | Có | Thao tác còn tùy mutability/null contract. |
| `remove(0)`, `remove("A")` | Có | Một bên xóa theo chỉ số, một bên theo Object. |
| `clear()`, `Collections.reverse(list)` | Có | Runtime list phải hỗ trợ sửa đổi cần thiết. |

```java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
List<?> view = values;
Object removed = view.remove(1);
Collections.reverse(view);
System.out.println(removed + " / " + values); // B / [C, A]
```

Các lời gọi này không chèn phần tử sai kiểu, nhưng vẫn thay đổi dữ liệu. Phần kế tiếp phân biệt cụ thể `ArrayList`, `Arrays.asList` và `List.of` để lý giải tại sao cùng một lời gọi đúng kiểu có thể thành công hoặc ném `UnsupportedOperationException`.

## 6. Phân biệt ba loại danh sách thường gặp

| Danh sách | `add(null)` | `set(0, null)` | `remove(0)` |
| --- | --- | --- | --- |
| `new ArrayList<>(List.of("A"))` | Thường thành công | Thành công | Thành công |
| `Arrays.asList("A")` | `UnsupportedOperationException` | Thành công | `UnsupportedOperationException` |
| `List.of("A")` | `UnsupportedOperationException` | `UnsupportedOperationException` | `UnsupportedOperationException` |

Cả ba trường hợp đều có thể được gán cho một biến `List<?>`. Chúng khác nhau ở **hợp đồng sửa đổi của đối tượng cụ thể**:

1. `ArrayList` thông thường cho phép thêm, thay, xóa và chấp nhận `null`.
2. `Arrays.asList` trả về danh sách có **kích thước cố định**, liên kết với mảng nền: cho phép `set` nhưng không cho thêm hoặc xóa làm đổi kích thước.
3. `List.of` trả về danh sách **không thể sửa đổi**; không cho `add`, `set`, `remove`, và không cho chứa `null`.

Không nên đánh đồng "bất biến theo tham số kiểu của generics" (*invariance*) với "không thể sửa đổi dữ liệu" (*unmodifiable/immutable collection*).

## 7. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `WildcardMutationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class WildcardMutationDemo {
    // Helper giữ cùng một T khi vừa đọc vừa ghi giá trị đã có.
    private static <T> void swap(List<T> items, int left, int right) {
        T first = items.get(left);
        items.set(left, items.get(right));
        items.set(right, first);
    }

    static void swapFirstTwo(List<?> items) {
        if (items.size() >= 2) {
            swap(items, 0, 1); // Java capture kiểu của '?' khi gọi helper.
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(Arrays.asList("Java", "Generics", "List"));
        List<?> unknown = words;

        System.out.println("Read: " + unknown.get(0));

        Object old = unknown.set(1, null);
        System.out.println("Old: " + old);
        System.out.println("After set null: " + words);

        unknown.remove(1);
        System.out.println("After remove: " + words);

        swapFirstTwo(unknown);
        System.out.println("After swap: " + words);

        unknown.add(null);
        System.out.println("After add null: " + words);

        try {
            List<?> fixed = List.of("immutable");
            fixed.add(null);
        } catch (UnsupportedOperationException e) {
            System.out.println(
                    "Unmodifiable: " + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 WildcardMutationDemo.java
java WildcardMutationDemo
```

Kết quả:

```text
Read: Java
Old: Generics
After set null: [Java, null, List]
After remove: [Java, List]
After swap: [List, Java]
After add null: [List, Java, null]
Unmodifiable: UnsupportedOperationException
```

Diễn giải:

- `unknown.get(0)` đọc `String` dưới dạng `Object`; thao tác in vẫn hiện nội dung chuỗi.
- `set(1, null)` thay `Generics` bằng `null`; biến `old` giữ giá trị cũ.
- `remove(1)` xóa phần tử `null`, còn `[Java, List]`.
- Helper `swap` bắt giữ kiểu phần tử cùng một `T`, cho phép đổi hai phần tử mà không cần ép kiểu và không thêm giá trị sai kiểu.
- `add(null)` thành công với `ArrayList`.
- `List.of` từ chối `add` tại runtime dù đối số `null` hợp lệ về mặt generic.

## 8. Khi cần thêm hoặc thay bằng một giá trị thật: chọn kiểu API khác

### 8.1. Biết chính xác kiểu phần tử: dùng `List<T>`

Nếu phương thức phải thao tác với chuỗi, khai báo rõ:

```java
static void replaceFirst(List<String> list, String replacement) {
    if (!list.isEmpty()) {
        list.set(0, replacement);
    }
}
```

Phương thức chỉ nhận `List<String>` (và các triển khai của nó) nên có thể thay bằng `String`. Trình biên dịch kiểm tra kiểu của giá trị mới.

### 8.2. Cùng kiểu chưa biết: dùng type parameter và wildcard capture

Nếu phương thức phải đọc phần tử đã có rồi đưa nó vào lại danh sách hoặc hoán đổi hai phần tử, dùng `<T>` để giữ quan hệ giữa giá trị và danh sách:

```java
static <T> void rotateFirstTwo(List<T> list) {
    if (list.size() < 2) {
        return;
    }
    T first = list.get(0);
    list.set(0, list.get(1));
    list.set(1, first);
}
```

Một biến `List<?>` vẫn truyền được vào phương thức này vì compiler có thể capture kiểu wildcard cho **cả lời gọi**:

```java
List<?> list = new ArrayList<>(List.of(1, 2));
rotateFirstTwo(list); // Hợp lệ nếu đối tượng hỗ trợ set
```

Điểm mấu chốt: `<T>` không cho phép nhét kiểu tùy ý vào danh sách; nó buộc **các vị trí dùng `T` thống nhất với nhau**.

### 8.3. Muốn thêm giá trị kiểu `T`: dùng `? super T`

Đối với phương thức chỉ nhận dữ liệu để ghi:

```java
static void appendText(List<? super String> destination) {
    destination.add("Java");
}
```

Phương thức chấp nhận `List<String>` và `List<Object>`, vì cả hai đều có thể chứa một `String`. Ngược lại, `List<?>` không bảo đảm điều này.

### 8.4. Muốn đọc với giới hạn trên: dùng `? extends T`

```java
static double total(List<? extends Number> source) {
    double result = 0;
    for (Number number : source) {
        result += number.doubleValue();
    }
    return result;
}
```

`? extends Number` hữu ích để **đọc** giá trị như `Number`, nhưng vẫn không cho `source.add(1)` hay `source.set(0, 1)`. Giới hạn trên không làm cho kiểu phần tử cụ thể trở nên xác định.

## 9. Lỗi phổ biến và hướng xử lý

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `List<?>` cho phép `add(Object)` | Kiểu phần tử thực tế có thể hẹp hơn `Object` | Dùng `List<Object>` khi đối tượng thực sự phải chứa mọi `Object`, hoặc `? super T` để nhận `T` |
| `List<?>` luôn chỉ đọc | `remove`, `clear`, `set(..., null)`, hoán đổi có thể biên dịch | Xem riêng hợp đồng thay đổi của implementation |
| `add(null)` luôn thành công | `List.of` không hỗ trợ sửa đổi; triển khai khác có thể không nhận `null` | Kiểm tra hợp đồng danh sách; tránh chèn `null` khi không cần |
| `set(index, x)` được phép chỉ vì không đổi kích thước | Nó vẫn đưa giá trị `x` mới vào vị trí có kiểu phần tử chưa biết | Dùng `List<T>` hoặc `List<? super T>` thích hợp |
| `list.set(0, list.get(0))` chắc chắn hợp lệ với `List<?>` | Hai lần dùng wildcard có thể thành các capture không tương thích | Đưa cả thao tác đọc và ghi vào helper `<T>` |
| Ép `List<?>` thành `List<String>` để thêm giá trị | Ép kiểu unchecked không chứng minh danh sách thật chứa `String`; có thể tạo heap pollution | Tạo API có type parameter đúng ngay từ đầu |
| `Collections.swap` hoạt động nên `list.add("x")` cũng phải hoạt động | Swap chỉ chuyển các giá trị đã cùng nằm trong danh sách; add đưa giá trị bên ngoài vào | Phân biệt sắp xếp phần tử hiện có và chèn phần tử mới |

**Đừng dùng raw type** (ví dụ `List raw = unknown;`) như cách vượt giới hạn. Raw type bỏ qua phần lớn kiểm tra generic ở bước biên dịch, có thể gây lỗi ép kiểu về sau khi phần tử được đọc qua một tham chiếu có kiểu cụ thể.

## 10. Tự kiểm tra: biên dịch hay lỗi runtime?

Dự đoán kết quả của mỗi đoạn **độc lập** sau, giả sử đã import `java.util.*`.

**A — Thêm phần tử cụ thể**

```java
List<?> a = new ArrayList<String>();
a.add("X");
```

**B — Thêm `null` vào danh sách sửa được**

```java
List<?> b = new ArrayList<String>();
b.add(null);
System.out.println(b.size());
```

**C — Thay bằng `null` trên danh sách không sửa được**

```java
List<?> c = List.of("X");
c.set(0, null);
```

**D — Hoán đổi phần tử trên danh sách có thể sửa**

```java
List<?> d = new ArrayList<>(List.of("X", "Y"));
Collections.swap(d, 0, 1);
System.out.println(d);
```

**E — Đọc rồi truyền thẳng vào `set`**

```java
List<?> e = new ArrayList<>(List.of("X"));
e.set(0, e.get(0));
```

**Đáp án:**

- **A:** Không biên dịch; `String` không được bảo đảm là kiểu phần tử của `List<?>`.
- **B:** Biên dịch và chạy thành công với `ArrayList`; in `1`.
- **C:** Biên dịch được, nhưng `List.of` ném `UnsupportedOperationException` khi gọi `set`.
- **D:** Biên dịch và chạy thành công; in `[Y, X]`.
- **E:** Không biên dịch vì wildcard capture trong lời gọi `get` không thống nhất với kiểu tham số mà `set` yêu cầu. Có thể dùng helper `<T>` để bảo đảm cả hai vị trí cùng một kiểu.

## 11. Tổng kết

Đối với `List<?>`, trình biên dịch **không chấp nhận chèn hay thay thế bằng một giá trị khác `null`** vì kiểu phần tử chưa biết. `add(null)` và `set(index, null)` hợp lệ về mặt kiểu nhưng không bảo đảm chạy thành công. Xóa, làm rỗng và sắp xếp lại phần tử có thể hợp lệ về kiểu; chúng vẫn tuân theo khả năng sửa đổi thực tế của đối tượng danh sách.

Khi cần ghi dữ liệu thật, hãy mô tả quan hệ kiểu rõ ràng bằng `List<T>`, `List<? super T>` hoặc helper generic `<T>`. Wildcard `?` giúp API nhận nhiều kiểu danh sách, nhưng vẫn giữ nguyên bảo đảm an toàn kiểu của Java.
