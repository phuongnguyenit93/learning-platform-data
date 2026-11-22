# Phân biệt hàm `map` trả về `null` với `flatMap` trả về `null` trong `Optional`

Trong Java, `Optional<T>` mô tả một kết quả **có giá trị** hoặc **không có giá trị**. Khi dùng API hàm bậc cao, `Optional.map` và `Optional.flatMap` đều chỉ gọi hàm chuyển đổi khi `Optional` ban đầu có giá trị, nhưng chúng **xử lý kết quả `null` của hàm chuyển đổi hoàn toàn khác nhau**:

- **`optional.map(mapper)`**: nếu `mapper` trả về `null`, kết quả là `Optional.empty()`, không ném lỗi chỉ vì kết quả mapper null.
- **`optional.flatMap(mapper)`**: `mapper` bắt buộc trả về **một đối tượng `Optional` không null**. Nếu mapper thực sự được gọi và trả về `null`, `flatMap` ném `NullPointerException`.
- Nếu `Optional` nguồn **đang empty**, cả hai đều không gọi mapper, nên kết quả tiếp tục là `Optional.empty()`; trường hợp này không làm lộ lỗi “mapper trả về null” của `flatMap`.

Điểm phân biệt nằm ở **hợp đồng kiểu trả về của hàm chuyển đổi** và cách `Optional` biểu diễn sự vắng mặt, không nằm ở việc `map` “an toàn hơn” trong mọi tình huống.

## 1. Đọc chữ ký để hiểu đúng bản chất

Với Java 17, hai phương thức có dạng:

~~~java
// Chữ ký API để tham khảo; không phải chương trình Java độc lập.
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper);

public <U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper);
~~~

Trong `map`, hàm `mapper` trả về **giá trị thường `U`**. Giá trị đó có thể là `null`, và API chuyển nó thành trạng thái rỗng bằng logic tương đương `Optional.ofNullable(result)`.

Trong `flatMap`, `mapper` trả về **`Optional` bao quanh `U`**. `flatMap` sử dụng chính đối tượng `Optional` trả về để tránh lồng nhiều lớp; không tự biến một tham chiếu `Optional` bằng `null` thành `Optional.empty()`.

Có thể hình dung **trường hợp nguồn có giá trị** bằng mã giả:

~~~java
// Mã giả: mô tả ý tưởng, không sao chép mã nguồn JDK.
Optional<U> mapLike(T value, Function<T, U> mapper) {
    return Optional.ofNullable(mapper.apply(value));
}

Optional<U> flatMapLike(T value,
                        Function<T, Optional<U>> mapper) {
    return Objects.requireNonNull(mapper.apply(value));
}
~~~

Hai hàm minh họa trên không phải là các phương thức đầy đủ trong lớp `Optional`. Trên `Optional` nguồn empty, mapper không được gọi. Bản thân **tham số `mapper` phải khác null**: truyền trực tiếp `map(null)` hoặc `flatMap(null)` đều không hợp lệ và sẽ ném `NullPointerException`, kể cả khi `Optional` nguồn empty.

## 2. Ví dụ thực thi: `map` nhận kết quả null, `flatMap` không nhận

Tạo file `OptionalNullMappingDemo.java`:

~~~java
import java.util.Optional;

public class OptionalNullMappingDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("Java");
        Optional<String> absent = Optional.empty();

        Optional<Integer> mapNull = present.map(s -> null);
        System.out.println("map(null result)=" + mapNull);

        try {
            Optional<Integer> flatMapNull = present.flatMap(s -> null);
            System.out.println(flatMapNull);
        } catch (NullPointerException e) {
            System.out.println("flatMap(null result)=NullPointerException");
        }

        Optional<Integer> emptyMap = absent.map(s -> null);
        Optional<Integer> emptyFlatMap = absent.flatMap(s -> null);
        System.out.println("empty.map=" + emptyMap);
        System.out.println("empty.flatMap=" + emptyFlatMap);

        Optional<Integer> correct = present.flatMap(
                s -> Optional.ofNullable((Integer) null));
        System.out.println("correct.flatMap=" + correct);
    }
}
~~~

~~~bash
javac --release 17 OptionalNullMappingDemo.java
java OptionalNullMappingDemo
~~~

Kết quả:

~~~text
map(null result)=Optional.empty
flatMap(null result)=NullPointerException
empty.map=Optional.empty
empty.flatMap=Optional.empty
correct.flatMap=Optional.empty
~~~

Các giá trị cần chú ý:

1. `present.map(s -> null)` **trả về `Optional.empty()`**, vì kết quả ánh xạ là null.
2. `present.flatMap(s -> null)` **ném `NullPointerException`** vì hàm đã chạy và trả về một tham chiếu `Optional` bằng null. Dòng in bên trong `try` không thực hiện.
3. `absent.flatMap(s -> null)` **không ném lỗi** trong ví dụ này vì mapper không chạy khi nguồn empty; kết quả vẫn empty.
4. `present.flatMap(s -> Optional.ofNullable((Integer) null))` hợp lệ vì mapper trả về **đối tượng `Optional.empty()` thực sự**, không phải một biến tham chiếu null.

Không nên suy luận từ việc `empty.flatMap(s -> null)` chạy thành công rằng mapper trả về null là hợp lệ. Nó chỉ chưa được gọi. Viết test với nguồn có giá trị để kiểm tra hợp đồng của mapper.

## 3. `map` trả về `Optional.empty()` khi trường được lấy ra null

Một trường hợp phổ biến là getter trả về giá trị nullable. Nếu muốn biến nullable thành `Optional`, `map` làm điều đó tự nhiên.

Tạo file `NullableGetterDemo.java`:

~~~java
import java.util.Optional;

public class NullableGetterDemo {
    record Account(String id, String nickname) {}

    public static void main(String[] args) {
        Optional<Account> account =
                Optional.of(new Account("A-1", null));

        Optional<String> nickname = account.map(Account::nickname);
        String display = nickname.orElse("(chưa đặt tên)");

        System.out.println("nickname=" + nickname);
        System.out.println("display=" + display);
    }
}
~~~

~~~bash
javac --release 17 NullableGetterDemo.java
java NullableGetterDemo
~~~

Kết quả:

~~~text
nickname=Optional.empty
display=(chưa đặt tên)
~~~

Ở đây, `Account::nickname` trả về `String`, nên **`map` là lựa chọn phù hợp**. Khi nickname null, sự vắng mặt được biểu diễn bằng `Optional.empty()`.

Nếu một getter **được định nghĩa trả về `Optional<String>`**, ví dụ `Account::findNickname`, thì `flatMap` thường phù hợp hơn để khỏi tạo `Optional<Optional<String>>`. Cần phân biệt getter nullable với getter trả về `Optional`.

## 4. `flatMap` dùng để tránh `Optional<Optional<T>>`

Khi hàm chuyển đổi tự trả về `Optional<U>`, dùng `map` sẽ giữ nguyên lớp `Optional` bên trong:

~~~java
Optional<Optional<Integer>> nested =
        Optional.of("42").map(s -> Optional.of(Integer.parseInt(s)));
~~~

Đây là **đoạn minh họa** nằm trong phương thức có `import java.util.Optional`. Kiểu của `nested` là `Optional<Optional<Integer>>`, gây bất tiện khi sử dụng.

Dùng `flatMap` sẽ gộp hai lớp:

~~~java
Optional<Integer> flat =
        Optional.of("42").flatMap(s -> Optional.of(Integer.parseInt(s)));
~~~

Khi lambda trả về `Optional.empty()`, `flatMap` trả về empty hoàn toàn bình thường. Vấn đề chỉ phát sinh khi **chính biến tham chiếu đến đối tượng `Optional` là null**.

Bảng đối chiếu cho `Optional.of("x")`:

| Hàm chuyển đổi | Gọi bằng `map` | Gọi bằng `flatMap` |
| --- | --- | --- |
| `s -> "y"` | `Optional["y"]` | Không biên dịch: `String` không phải `Optional`. |
| `s -> null` | `Optional.empty()` | `NullPointerException` khi mapper được gọi. |
| `s -> Optional.of("y")` | `Optional[Optional["y"]]` | `Optional["y"]`. |
| `s -> Optional.empty()` | `Optional[Optional.empty]` | `Optional.empty()`. |
| `s -> Optional.ofNullable(null)` | `Optional[Optional.empty]` | `Optional.empty()`. |

**Chú thích:** các dạng trong bảng là ký hiệu kết quả `Optional` để dễ so sánh; không phải các biểu thức constructor có thể viết trực tiếp trong Java. `map` và `flatMap` phân biệt rõ hai loại hàm: `T -> U` so với `T -> Optional<U>`.

## 5. Chuyển một hàm nullable thành mapper cho `flatMap`

Có thể bạn đang có API cũ trả về một giá trị thường hoặc null:

~~~java
// Hợp đồng minh họa: null nghĩa là không tìm thấy.
static String lookupEmail(String username) {
    return username.equals("an") ? "an@example.com" : null;
}
~~~

Hàm này trả về `String`, nên dùng `map`:

~~~java
Optional<String> email = Optional.of("binh")
        .map(LegacyDirectory::lookupEmail);
~~~

**Hai đoạn trên minh họa chữ ký và cách gọi; `LegacyDirectory` cần được khai báo đầy đủ trong chương trình thực.**

Nếu pipeline đã thiết kế xoay quanh `flatMap`, viết adapter trả về `Optional` bằng `ofNullable`:

~~~java
Optional<String> email = Optional.of("binh")
        .flatMap(name -> Optional.ofNullable(lookupEmail(name)));
~~~

Cách trên nằm trong cùng lớp có phương thức `lookupEmail`. Sự khác nhau mang tính hợp đồng:

- `map(name -> lookupEmail(name))`: biến `String` hoặc null thành `Optional<String>`.
- `flatMap(name -> Optional.ofNullable(lookupEmail(name)))`: chuyển kết quả nullable thành `Optional<String>` **bên trong** mapper, rồi trả đúng kiểu mà `flatMap` yêu cầu.
- `flatMap(name -> lookupEmail(name))` với `lookupEmail` trả `String`: **không biên dịch**, vì kiểu trả về của mapper không phải một `Optional`.

Nếu API thực sự có phương thức trả `Optional<String>`, hãy ưu tiên `flatMap(directory::findEmail)` và đảm bảo phương thức `findEmail` **không bao giờ trả về null**, mà trả `Optional.empty()` khi không tìm thấy.

### Ví dụ độc lập: tương thích API nullable và API Optional

Tạo file `OptionalAdapterDemo.java`:

~~~java
import java.util.Optional;

public class OptionalAdapterDemo {
    static String legacyLookup(String name) {
        return name.equals("an") ? "an@example.com" : null;
    }

    static Optional<String> safeLookup(String name) {
        return Optional.ofNullable(legacyLookup(name));
    }

    public static void main(String[] args) {
        Optional<String> absentByMap =
                Optional.of("binh").map(OptionalAdapterDemo::legacyLookup);
        Optional<String> absentByFlatMap =
                Optional.of("binh").flatMap(OptionalAdapterDemo::safeLookup);
        Optional<String> presentByFlatMap =
                Optional.of("an").flatMap(OptionalAdapterDemo::safeLookup);

        System.out.println("map=" + absentByMap);
        System.out.println("flatMap=" + absentByFlatMap);
        System.out.println("found=" + presentByFlatMap);
    }
}
~~~

~~~bash
javac --release 17 OptionalAdapterDemo.java
java OptionalAdapterDemo
~~~

Kết quả:

~~~text
map=Optional.empty
flatMap=Optional.empty
found=Optional[an@example.com]
~~~

API `safeLookup` bảo đảm trả về `Optional` hợp lệ cả khi hệ thống cũ trả null; cách này biến `flatMap` thành đoạn ghép an toàn.

## 6. Tránh lẫn “`Optional.empty()`” với “tham chiếu `Optional` bằng null”

Cả hai có thể ám chỉ “không có giá trị” trong văn nói, nhưng ở cấp đối tượng Java chúng khác nhau:

~~~java
Optional<String> empty = Optional.empty();
Optional<String> invalid = null;
~~~

- `empty` là **đối tượng `Optional` có trạng thái rỗng**. Có thể gọi `empty.isPresent()`, `empty.orElse(...)` và sử dụng trong `flatMap`.
- `invalid` là **tham chiếu null**, không phải một `Optional`. Gọi bất kỳ instance method nào qua nó có thể ném `NullPointerException`.
- Hợp đồng tốt cho phương thức khai báo trả về `Optional<T>` là trả `Optional.empty()` khi vắng mặt, **không trả null**.
- `Optional.of(null)` ném `NullPointerException`; `Optional.ofNullable(null)` trả `Optional.empty()`.
- Một `Optional` có giá trị không chứa null bên trong; `Optional.ofNullable` dùng null để biểu diễn sự vắng mặt chứ không lưu null làm “giá trị hiện diện”.

Đừng sửa lỗi mapper `flatMap` trả null bằng cách bọc `orElse` **sau** `flatMap`:

~~~java
// Sai khi findOptionalValue() có thể trả về tham chiếu null:
// source.flatMap(x -> findOptionalValue(x)).orElse(fallback);
~~~

Vì `NullPointerException` xuất hiện **trước** khi `orElse` được thực thi. Cần sửa API `findOptionalValue` để trả `Optional.empty()`, hoặc xử lý tham chiếu null ngay tại nguồn theo một hợp đồng rõ ràng.

## 7. Trường hợp `Optional` nguồn empty có thể che lỗi

Khi nguồn `Optional.empty()`, cả `map` và `flatMap` đều bỏ qua mapper. Điều này là ý nghĩa cốt lõi của phép biến đổi trên Optional, nhưng cũng có hệ quả kiểm thử:

~~~java
// Đoạn minh họa chạy trong phương thức:
Optional<String> empty = Optional.empty();

Optional<Integer> result =
        empty.flatMap(s -> {
            throw new IllegalStateException("should not run");
        });
// result == Optional.empty(), lambda không chạy.
~~~

Lỗi nằm trong mapper có thể bị che nếu test chỉ dùng nguồn empty. Kiểm thử đúng nên có ít nhất ba nhóm: (1) nguồn empty, (2) nguồn present với mapper trả `Optional.of(value)`, (3) nguồn present với mapper trả `Optional.empty()`; có thể bổ sung test cố ý trả null để xác nhận API vi phạm hợp đồng và phát sinh `NullPointerException`.

Đối với `map`, nên có test cho mapper trả null nếu null là một khả năng hợp lệ của API. Đồng thời, cần xác minh việc biến null thành empty có đúng chính sách nghiệp vụ hay đang che giấu một lỗi dữ liệu bất ngờ.

## 8. Thực tế với các tầng dữ liệu lồng nhau

Giả sử một hồ sơ `User` có thể thiếu `Profile`, và `Profile` có thể thiếu `displayName`. Có thể dùng chuỗi `map` với các getter nullable: mỗi bước chuyển kết quả null thành empty, các bước tiếp theo được bỏ qua.

Tạo file `OptionalNestedDataDemo.java`:

~~~java
import java.util.Optional;

public class OptionalNestedDataDemo {
    record Profile(String displayName) {}
    record User(String id, Profile profile) {}

    static Optional<User> findUser(boolean hasProfile) {
        return Optional.of(new User(
                "u-1", hasProfile ? new Profile(null) : null));
    }

    public static void main(String[] args) {
        String a = findUser(false)
                .map(User::profile)
                .map(Profile::displayName)
                .orElse("(ẩn)");

        String b = findUser(true)
                .flatMap(user -> Optional.ofNullable(user.profile()))
                .flatMap(profile ->
                        Optional.ofNullable(profile.displayName()))
                .orElse("(ẩn)");

        System.out.println("without profile=" + a);
        System.out.println("without name=" + b);
    }
}
~~~

~~~bash
javac --release 17 OptionalNestedDataDemo.java
java OptionalNestedDataDemo
~~~

Kết quả:

~~~text
without profile=(ẩn)
without name=(ẩn)
~~~

Đây là hai cách hợp lệ nhưng có ý nghĩa khác nhau ở mức API:

- Với getter trả giá trị nullable, `map(User::profile).map(Profile::displayName)` gọn và đúng: từng tầng null trở thành empty.
- Với chức năng hoặc repository trả `Optional<Profile>` và `Optional<String>`, dùng `flatMap` để không lồng Optional.
- Trong ví dụ dùng `flatMap` dù getter nullable, lambda đã **bọc getter bằng `Optional.ofNullable`**. Nếu thay bằng `flatMap(User::profile)`, Java không biên dịch vì `profile()` trả `Profile` thay vì `Optional`.

Không dùng `Optional.get()` vô điều kiện ở cuối pipeline: sau bước `map` trả null hoặc `flatMap` trả `Optional.empty()`, kết quả có thể empty và `get()` ném `NoSuchElementException`. Ưu tiên `orElse`, `orElseGet`, `orElseThrow` với ngữ nghĩa nghiệp vụ cụ thể.

## 9. Phân biệt với `Stream.flatMap`

Tên `flatMap` được dùng ở nhiều API Java, **nhưng hành vi với mapper trả null không đồng nhất**:

- `Optional.flatMap`: nếu có phần tử và mapper trả về một **tham chiếu `Optional` null**, ném `NullPointerException`.
- `Stream.flatMap`: mapper trả một `Stream`; theo hợp đồng Stream, nếu mapped stream là null thì **được xử lý như một stream rỗng**.

Ví dụ đầy đủ `StreamFlatMapNullDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class StreamFlatMapNullDemo {
    public static void main(String[] args) {
        List<String> values = Stream.of("a", "b", "c")
                .flatMap(s -> s.equals("b") ? null : Stream.of(s))
                .toList();
        System.out.println(values);
    }
}
~~~

~~~bash
javac --release 17 StreamFlatMapNullDemo.java
java StreamFlatMapNullDemo
~~~

Kết quả:

~~~text
[a, c]
~~~

Không áp dụng suy luận từ `Stream.flatMap` sang `Optional.flatMap`, hoặc ngược lại. Luôn đọc hợp đồng của chính API. Cách làm rõ nghĩa và thuận tiện khi làm việc với stream là trả `Stream.empty()` thay vì null, kể cả khi API cho phép null.

## 10. Khi nào nên chọn `map` và `flatMap`?

| Hàm bạn đang gọi | Ví dụ chữ ký | Phương thức nên dùng | Khi không có dữ liệu |
| --- | --- | --- | --- |
| Trả giá trị thông thường, không nullable | `int length(String s)` | `map` | Nếu nguồn empty thì kết quả empty. |
| Trả giá trị thông thường, có thể null | `String nickname(User u)` | `map` | `null` từ mapper thành empty. |
| Trả Optional đúng hợp đồng | `Optional<User> find(String id)` | `flatMap` | Mapper trả `Optional.empty()`. |
| Trả `Optional` nhưng đôi khi trả null | `Optional<User> brokenFind(...)` | Sửa hợp đồng của hàm | `flatMap` sẽ ném NPE khi mapper chạy và trả null. |
| Muốn giữ Optional lồng nhau có chủ đích | `Optional<U> find(...)` | `map` | Kết quả có thể là `Optional<Optional<U>>`. |

**Lưu ý về dữ liệu và lỗi:** `map` tự chuyển mapper-result null thành empty; đôi khi đây là cách diễn đạt đúng việc thiếu dữ liệu, đôi khi lại che một lỗi mà nghiệp vụ mong muốn phát hiện. Nếu mapper **không được phép** trả null, có thể dùng `Objects.requireNonNull(...)` trong mapper để fail-fast thay vì âm thầm coi là vắng mặt:

~~~java
// Đoạn minh họa, dùng khi nickname được yêu cầu luôn khác null.
Optional<String> nickname = account.map(
        a -> java.util.Objects.requireNonNull(
                a.nickname(), "nickname must not be null"));
~~~

Nếu yêu cầu là dữ liệu nullable hợp lệ, dùng cách ánh xạ mặc định của `Optional.map`. Nếu yêu cầu là hàm trả `Optional`, thiết kế mapper luôn trả **một Optional không null**.

## 11. Checklist xử lý lỗi thực tế

1. Kiểm tra `Optional` **nguồn đang present hay empty**. Với nguồn empty, mapper không chạy và test có thể không bộc lộ lỗi.
2. Xác định kiểu trả về thực của mapper: `U`, `U` nullable, `Optional<U>` hay tham chiếu `Optional<U>` có thể null?
3. Nếu mapper trả nullable `U`, dùng `map`; null được diễn giải thành empty.
4. Nếu mapper trả `Optional<U>`, dùng `flatMap` và bảo đảm trả `Optional.empty()` khi không tìm thấy.
5. Khi nhận API legacy trả giá trị nullable nhưng muốn ghép qua `flatMap`, bọc giá trị bằng `Optional.ofNullable(...)` ở **bên trong mapper**.
6. Không dùng `orElse` để chữa ngoại lệ của `flatMap` đã xảy ra, không dùng `Optional.of(null)`, không trả null từ phương thức có chữ ký `Optional<T>`.
7. Thử cả giá trị có mặt, giá trị vắng mặt, mapper trả empty, và tình huống mapper vi phạm hợp đồng.
8. Không suy diễn cách xử lý null của `Optional.flatMap` từ `Stream.flatMap`.

**Ghi nhớ:** với `Optional` nguồn có giá trị, **`map(x -> null)` trả `Optional.empty()`**, còn **`flatMap(x -> null)` ném `NullPointerException`**. Với `flatMap`, “không có kết quả” phải được biểu diễn bằng **`Optional.empty()`**, tức một đối tượng Optional hợp lệ, chứ không phải tham chiếu null.