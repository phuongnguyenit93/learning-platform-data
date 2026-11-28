# Không phụ thuộc lớp triển khai cụ thể của danh sách kết quả

`Stream.toList()` trả về kiểu `List<T>` không sửa đổi được. Hợp đồng API không cam kết object kết quả là `ArrayList`, `LinkedList` hay bất kỳ lớp triển khai cụ thể nào. Vì vậy, hãy sử dụng kết quả thông qua interface `List` và dựa vào những hành vi được Java API bảo đảm.

Nếu chương trình thật sự cần một implementation cụ thể, chẳng hạn `ArrayList` mutable để thêm, xóa hoặc truy cập theo chỉ số thường xuyên, hãy yêu cầu loại collection đó ngay khi thu thập bằng `Collectors.toCollection(ArrayList::new)`. Không ép kiểu kết quả của `toList()` hoặc kiểm tra tên lớp nội bộ để điều khiển logic.

## 1. Hợp đồng công khai là `List<T>`, không phải `ArrayList<T>`

Chữ ký của `Stream.toList()` là:

```java
default List<T> toList()
```

Kiểu trả về công khai là `List<T>`. Javadoc quy định danh sách kết quả không sửa đổi được, nhưng không chỉ định lớp triển khai. Điều này cho phép JDK lựa chọn cách biểu diễn nội bộ phù hợp với pipeline, nguồn dữ liệu và các tối ưu hóa của từng phiên bản.

Ví dụ:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .toList();

System.out.println(names);       // [An, Bình, Chi]
System.out.println(names.get(0)); // An
System.out.println(names.size()); // 3
```

Đoạn mã chỉ sử dụng các thao tác mà interface `List` cung cấp. Đây là cách dùng ổn định vì chương trình phụ thuộc vào hợp đồng công khai thay vì chi tiết triển khai của một JDK cụ thể.

Không nên suy luận rằng vì một phiên bản JDK hiện tại trả về một lớp nội bộ nào đó thì mọi phiên bản Java hoặc mọi implementation của Stream đều phải trả về cùng lớp đó.

## 2. Không ép kiểu kết quả thành `ArrayList`

Đoạn mã sau không an toàn:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

ArrayList<String> editableNames = (ArrayList<String>) names;
// Có thể ném ClassCastException khi chạy
```

Compiler cho phép cast từ `List<String>` sang `ArrayList<String>` vì hai kiểu có quan hệ kế thừa/interface phù hợp để thực hiện phép kiểm tra lúc chạy. Tuy nhiên, object thực tế được trả về không được API cam kết là `ArrayList`. Nếu lớp thực tế không phải `ArrayList`, cast sẽ ném `ClassCastException`.

Ngay cả khi phép cast tình cờ chạy được trên một JDK, đoạn mã vẫn phụ thuộc vào implementation detail. Thay đổi JDK, cách tối ưu pipeline hoặc implementation Stream có thể làm giả định đó không còn đúng.

Hãy giữ kiểu khai báo là `List<T>` nếu chương trình chỉ cần hợp đồng `List`:

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");

List<String> names = source.stream().toList();
```

Nếu cần `ArrayList`, hãy tạo `ArrayList` một cách tường minh như phần 6.

## 3. Không dùng tên lớp hoặc `getClass()` để quyết định nghiệp vụ

Không nên viết logic phụ thuộc vào tên lớp nội bộ hoặc lớp thực tế của danh sách:

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");

List<String> names = source.stream().toList();

// Không dùng các điều kiện kiểu này để quyết định cách xử lý:
// if (names instanceof ArrayList<?>) { ... }
// if (names.getClass().getName().contains("Immutable")) { ... }
```

Những kiểm tra đó không diễn đạt yêu cầu nghiệp vụ. Chúng chỉ nhận diện một implementation cụ thể hoặc một tên lớp có thể thay đổi. Nếu cần danh sách mutable, hãy yêu cầu mutable collection ngay từ nơi tạo ra nó. Nếu cần danh sách không sửa đổi được, hãy dựa vào hợp đồng của API đã chọn.

Trong trường hợp hiếm hoi chương trình thực sự cần một đặc tính bổ sung, hãy thể hiện đặc tính đó qua kiểu hoặc hợp đồng phù hợp. Ví dụ, `RandomAccess` là marker interface dành cho các danh sách hỗ trợ truy cập ngẫu nhiên hiệu quả; `List` nói chung không cam kết mọi implementation có cùng đặc tính hiệu năng. Nếu thuật toán phụ thuộc mạnh vào truy cập theo chỉ số, chọn `ArrayList` tường minh hoặc thiết kế lại thuật toán theo yêu cầu dữ liệu.

## 4. Dùng interface trong biến, tham số và kiểu trả về

Khi không cần implementation cụ thể, nên khai báo theo interface:

```java
import java.util.List;

class NameService {
    List<String> findNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .toList();
    }
}
```

Phương thức công bố rằng kết quả là `List<String>`. Người gọi có thể đọc, duyệt, lấy kích thước hoặc tạo stream tiếp theo mà không cần biết lớp triển khai.

Việc dùng interface giúp giảm phụ thuộc giữa các thành phần:

- Bên tạo dữ liệu có thể thay đổi cách thu thập hoặc implementation nội bộ mà không buộc caller đổi mã.
- Bên sử dụng chỉ cần hiểu hợp đồng `List`.
- Các test có thể kiểm tra nội dung và hành vi được công bố, không phải một tên lớp cụ thể.
- Mã nguồn ít bị ràng buộc với một phiên bản JDK hoặc một implementation Stream.

Nếu API cần trả về collection mutable, hãy ghi rõ điều đó trong Javadoc. Kiểu trả về `List<T>` tự nó không nói lên mutability, nên hợp đồng phương thức cần mô tả phần này.

## 5. Phân biệt hợp đồng `List` với đặc tính của object kết quả

Không phụ thuộc implementation không có nghĩa mọi hành vi đều không xác định. Những đặc tính được API quy định vẫn có thể được sử dụng:

| Đặc tính | Có thể dựa vào? | Giải thích |
| --- | --- | --- |
| Kiểu trả về là `List<T>` | Có | Đây là kiểu được công bố trong chữ ký phương thức. |
| Danh sách không sửa đổi được | Có | Mutator method ném `UnsupportedOperationException`. |
| Encounter order | Có điều kiện | Nếu stream có encounter order, danh sách giữ thứ tự đó. |
| Lớp thực tế là `ArrayList` | Không | API không cam kết implementation cụ thể. |
| Có thể ép kiểu sang `ArrayList` | Không | Phụ thuộc lớp thực tế và có thể ném `ClassCastException`. |
| Có thể tuần tự hóa | Không được bảo đảm | Không suy ra khả năng serializable từ kiểu `List`. |
| Identity của object kết quả | Không nên dựa vào | Kết quả có thể là value-based; thao tác phụ thuộc identity không đáng tin cậy. |
| Tốc độ truy cập chỉ số giống `ArrayList` | Không | `List` không cam kết mọi implementation có cùng đặc tính hiệu năng. |

Các thuộc tính này độc lập với nhau. Chẳng hạn, danh sách có thể không sửa đổi được nhưng vẫn cho phép phần tử `null`; unmodifiable không có nghĩa là lớp triển khai phải là một immutable collection class cụ thể.

## 6. Khi thật sự cần `ArrayList`, hãy tạo đúng loại collection

Nếu yêu cầu của chương trình là có một `ArrayList` mutable, dùng `Collectors.toCollection(ArrayList::new)`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("An", "Bình", "Chi");

ArrayList<String> names = source.stream()
    .filter(name -> !name.isBlank())
    .collect(Collectors.toCollection(ArrayList::new));

names.add("Dung"); // Hợp lệ
names.set(0, "Anh"); // Hợp lệ
```

Supplier `ArrayList::new` chỉ định rõ implementation cần tạo. Kết quả có kiểu `ArrayList<String>` và có thể sử dụng các đặc tính được `ArrayList` công bố.

Nếu đã có danh sách từ `toList()` và muốn tạo một bản làm việc mutable, dùng copy constructor:

```java
import java.util.ArrayList;
import java.util.List;

List<String> readOnlyNames = List.of("An", "Bình", "Chi").stream().toList();
ArrayList<String> editableNames = new ArrayList<>(readOnlyNames);

editableNames.add("Dung");
```

Hai cách khác nhau ở thời điểm tạo collection:

- `toCollection(ArrayList::new)` thu thập trực tiếp pipeline vào `ArrayList`.
- `new ArrayList<>(readOnlyNames)` sao chép một collection đã có thành danh sách mutable mới.

Copy constructor chỉ tạo bản sao nông. Nếu phần tử là object mutable, các danh sách vẫn có thể cùng tham chiếu tới object đó.

## 7. `Collectors.toList()` cũng không bảo đảm `ArrayList`

Không nên xem `Collectors.toList()` là cách thay thế để yêu cầu `ArrayList`. Hợp đồng của collector này không bảo đảm kiểu triển khai, khả năng sửa đổi, khả năng tuần tự hóa hoặc thread-safety của kết quả.

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("An", "Bình", "Chi");

List<String> names = source.stream()
    .collect(Collectors.toList());
```

Kiểu kết quả vẫn là `List<String>`. Một số implementation JDK có thể thường trả về `ArrayList`, nhưng đó không phải cam kết của API. Nếu code cần dựa vào mutability hoặc lớp collection cụ thể, hãy chọn `toCollection(...)`.

Tương tự, `Stream.toList()` cũng không nên được xem là cách yêu cầu một lớp immutable cụ thể. API chỉ cam kết danh sách không sửa đổi được và các hành vi được mô tả trong Javadoc.

## 8. Không dựa vào identity của danh sách

Javadoc hiện hành cho biết kết quả từ `Stream.toList()` có thể là *value-based*. Vì vậy, không sử dụng identity của danh sách làm một phần của logic chương trình:

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");

List<String> first = source.stream().toList();
List<String> second = source.stream().toList();

// Không dùng first == second để so sánh nội dung.
// Không dùng System.identityHashCode(first) làm mã định danh nghiệp vụ.
// Không dùng synchronized (first) làm khóa đồng bộ hóa.
```

Nếu cần so sánh nội dung, hãy dùng `equals()`:

```java
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");
List<String> first = source.stream().toList();
List<String> second = source.stream().toList();

boolean sameContents = first.equals(second);
```

Nếu cần một khóa đồng bộ hóa, tạo một object khóa riêng có identity ổn định và được quản lý rõ ràng. Không dùng một danh sách value-based làm monitor.

## 9. Kiểm thử hợp đồng, không kiểm thử implementation detail

Test nên xác minh điều API cam kết: nội dung, thứ tự khi nguồn có encounter order và việc không cho phép sửa đổi. Không nên kiểm tra lớp thực tế hoặc tên lớp nội bộ.

Ví dụ với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class StreamToListTest {
    @Test
    void returnsExpectedUnmodifiableList() {
        List<String> result = List.of("An", "Bình", "Chi").stream()
            .filter(name -> !name.isBlank())
            .toList();

        assertEquals(List.of("An", "Bình", "Chi"), result);
        assertThrows(UnsupportedOperationException.class,
            () -> result.add("Dung"));
    }
}
```

Test này không quan tâm danh sách bên trong được triển khai bằng lớp nào. Nếu JDK thay đổi implementation nhưng vẫn đáp ứng hợp đồng, test tiếp tục hợp lệ.

Tránh các assertion kiểu `assertInstanceOf(ArrayList.class, result)` hoặc so sánh `result.getClass().getName()`. Chúng biến một chi tiết nội bộ thành yêu cầu giả tạo của ứng dụng.

## 10. Cách chọn API theo yêu cầu

| Yêu cầu | Cách làm | Hợp đồng nhận được |
| --- | --- | --- |
| Chỉ cần danh sách để đọc | `stream.toList()` | `List<T>` unmodifiable. |
| Cần một `ArrayList` mutable | `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` cụ thể, có thể sửa đổi. |
| Đã có kết quả và cần bản làm việc mutable | `new ArrayList<>(result)` | `ArrayList` mới với cấu trúc độc lập. |
| Chỉ cần một `List`, không phụ thuộc mutability cụ thể | Khai báo `List<T>` và mô tả hợp đồng phương thức | Caller không bị ràng buộc vào implementation. |
| Cần thứ tự sắp xếp | Dùng `sorted(comparator)` trước `toList()` | Kết quả theo comparator, danh sách vẫn unmodifiable. |

## 11. Những điểm cần nhớ

- `Stream.toList()` trả `List<T>`; không có bảo đảm kết quả là `ArrayList` hay lớp cụ thể nào.
- Dùng các phương thức được `List` công bố và dựa vào hợp đồng unmodifiable của `toList()`.
- Không ép kiểu, kiểm tra tên lớp hoặc viết test phụ thuộc implementation nội bộ.
- Không giả định kết quả có thể tuần tự hóa hoặc có đặc tính hiệu năng như `ArrayList`.
- Tránh thao tác phụ thuộc identity vì kết quả có thể là value-based.
- Nếu cần implementation cụ thể, yêu cầu nó bằng `Collectors.toCollection(factory)` hoặc tạo bản sao phù hợp.

Hãy để API công khai quyết định mức độ phụ thuộc của mã nguồn. Khi chỉ cần một danh sách, làm việc qua `List<T>` giúp chương trình linh hoạt với thay đổi implementation. Khi cần đặc tính riêng của `ArrayList` hoặc collection khác, hãy yêu cầu loại đó một cách tường minh ở nơi tạo dữ liệu.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [List – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [ArrayList – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html)
- [Collectors.toCollection() và Collectors.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
