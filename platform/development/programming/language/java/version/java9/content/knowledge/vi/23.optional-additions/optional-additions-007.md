# Phân biệt Optional.or với giá trị mặc định trực tiếp trong Java

Java 9 bổ sung `Optional.or(Supplier)` để cung cấp một Optional thay thế khi Optional hiện tại rỗng. Phương thức này khác với `orElse(value)` và `orElseGet(supplier)`: `or` giữ nguyên kết quả ở dạng Optional, còn hai phương thức `orElse` trả về trực tiếp giá trị bên trong.

Ba cách viết có mục đích khác nhau:

- `orElse(defaultValue)`: trả về giá trị hiện có hoặc giá trị mặc định được truyền trực tiếp.
- `orElseGet(supplier)`: trả về giá trị hiện có hoặc gọi Supplier để tạo giá trị mặc định khi cần.
- `or(supplierOfOptional)`: trả về Optional hiện có hoặc gọi Supplier để tìm một Optional thay thế.

Điểm cần chú ý nhất là thời điểm đánh giá biểu thức mặc định, kiểu dữ liệu trả về và cách biểu diễn trường hợp không tìm thấy kết quả.

## 1. Optional biểu diễn giá trị có thể vắng mặt

`Optional<T>` là một đối tượng chứa tối đa một giá trị khác null. Một Optional có thể ở một trong hai trạng thái:

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> empty = Optional.empty();
~~~

- `Optional.of(value)` tạo Optional có giá trị và ném NullPointerException nếu value là null.
- `Optional.ofNullable(value)` tạo Optional rỗng khi value là null.
- `Optional.empty()` biểu diễn trạng thái không có giá trị.

Optional giúp API thể hiện rõ khả năng không tìm thấy dữ liệu, thay vì dùng null làm kết quả ngầm định. Khi xử lý Optional, cần quyết định giữ trạng thái vắng mặt để xử lý tiếp hay chuyển nó thành một giá trị mặc định.

## 2. orElse(value): dùng giá trị mặc định trực tiếp

Chữ ký:

~~~java
T orElse(T other)
~~~

Nếu Optional có giá trị, `orElse` trả về giá trị đó. Nếu Optional rỗng, phương thức trả về đối số `other`.

~~~java
String name = Optional.of("An").orElse("Không rõ");
String missing = Optional.<String>empty().orElse("Không rõ");
~~~

Kết quả:

- `name` là `"An"`.
- `missing` là `"Không rõ"`.

### Đối số được đánh giá trước khi gọi phương thức

Java đánh giá các đối số của lời gọi phương thức trước khi thực hiện lời gọi. Vì vậy, biểu thức truyền vào `orElse` luôn được đánh giá, kể cả khi Optional đã có giá trị.

~~~java
private static String createDefault() {
    System.out.println("Tạo giá trị mặc định");
    return "Mặc định";
}

String result = Optional.of("Đã có dữ liệu")
    .orElse(createDefault());
~~~

Đoạn mã vẫn in ra `Tạo giá trị mặc định`, dù kết quả cuối cùng là `Đã có dữ liệu`. Nếu biểu thức mặc định tốn tài nguyên, truy vấn cơ sở dữ liệu, đọc tệp hoặc có tác dụng phụ, việc đánh giá không cần thiết này có thể gây lãng phí hoặc làm thay đổi hành vi chương trình.

Dùng `orElse` phù hợp khi giá trị mặc định là hằng số, rẻ để tạo hoặc đã được tính sẵn và việc đánh giá luôn không gây vấn đề.

## 3. orElseGet(supplier): tạo giá trị mặc định khi cần

Chữ ký:

~~~java
T orElseGet(Supplier<? extends T> supplier)
~~~

Khác với `orElse`, `orElseGet` nhận một Supplier. Supplier chỉ được gọi khi Optional rỗng.

~~~java
String name = Optional.of("An")
    .orElseGet(() -> createDefault());

String missing = Optional.<String>empty()
    .orElseGet(() -> createDefault());
~~~

- Với Optional có giá trị, Supplier không được gọi.
- Với Optional rỗng, Supplier được gọi và giá trị trả về được dùng làm kết quả.

Có thể truyền method reference khi phương thức tạo giá trị không cần đối số:

~~~java
String name = optionalName.orElseGet(this::loadDefaultName);
~~~

### Chọn orElse hay orElseGet?

| Tiêu chí | orElse(value) | orElseGet(supplier) |
|---|---|---|
| Đối số | Giá trị T | Supplier tạo T |
| Thời điểm tạo giá trị mặc định | Trước khi gọi phương thức | Chỉ khi Optional rỗng |
| Khi Optional đã có giá trị | Biểu thức đối số vẫn được đánh giá | Supplier không được gọi |
| Phù hợp | Hằng số hoặc giá trị đã có sẵn | Giá trị cần tính toán, truy vấn hoặc tạo có chi phí |

Không nên mặc định `orElseGet` luôn tốt hơn. Với một hằng số đơn giản như `"UNKNOWN"`, `orElse("UNKNOWN")` thường dễ đọc hơn. Với một thao tác có chi phí hoặc tác dụng phụ, `orElseGet` thể hiện rõ ý định trì hoãn.

Nếu Supplier ném unchecked exception, ngoại lệ được truyền ra khi Supplier thực sự được gọi. Nếu Optional có giá trị và Supplier không được gọi, ngoại lệ trong thân Supplier không phát sinh.

## 4. or(supplierOfOptional): cung cấp một Optional thay thế

Chữ ký API từ Java 9:

~~~java
Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier
)
~~~

`or` nhận Supplier trả về một Optional. Nếu Optional hiện tại có giá trị, nó được giữ nguyên. Nếu Optional hiện tại rỗng, Supplier được gọi và Optional do Supplier trả về trở thành kết quả.

~~~java
Optional<String> name = findFromCache()
    .or(() -> findFromDatabase());
~~~

Nếu cache tìm thấy tên, truy vấn cơ sở dữ liệu không được thực hiện. Nếu cache rỗng, phương thức tìm trong cơ sở dữ liệu mới được gọi.

Điểm khác biệt chính là kết quả vẫn có kiểu `Optional<T>`. Nếu nguồn thay thế cũng không tìm thấy giá trị, nó có thể trả về `Optional.empty()` và trạng thái vắng mặt tiếp tục được giữ nguyên.

### Nối nhiều nguồn tìm kiếm

Đây là trường hợp sử dụng tiêu biểu của `or`:

~~~java
Optional<User> user = findInCache(userId)
    .or(() -> findInPrimaryDatabase(userId))
    .or(() -> findInArchive(userId));
~~~

Thứ tự tìm kiếm:

1. Kiểm tra cache.
2. Chỉ khi cache rỗng, kiểm tra cơ sở dữ liệu chính.
3. Chỉ khi nguồn chính cũng rỗng, kiểm tra kho lưu trữ.
4. Nếu tất cả nguồn đều rỗng, kết quả cuối cùng vẫn là `Optional.empty()`.

Các bước dự phòng được đánh giá lazy theo thứ tự. Khi đã có kết quả ở một bước, các Supplier phía sau không được gọi.

### Supplier phải trả về Optional khác null

`or` yêu cầu Supplier không null và kết quả từ `supplier.get()` cũng không được null. Nếu Supplier trả về null, phương thức ném NullPointerException. Hãy bọc một kết quả có thể null bằng `Optional.ofNullable`:

~~~java
Optional<String> fallback = optional.or(
    () -> Optional.ofNullable(loadNullableName())
);
~~~

Nếu `loadNullableName()` trả về null, Supplier trả về Optional rỗng. Khi đó kết quả của `or` vẫn là Optional rỗng.

Cần phân biệt hai trường hợp:

- `Optional.empty()`: hợp lệ, biểu diễn không tìm thấy kết quả thay thế.
- `null` thay cho Optional: không hợp lệ đối với hợp đồng của `or` và gây NullPointerException.

Ngay cả khi Optional hiện tại có giá trị, đối tượng Supplier truyền vào `or` vẫn phải khác null. Tuy nhiên, phương thức `get()` của Supplier chỉ được gọi khi Optional hiện tại rỗng.

## 5. So sánh ba cách xử lý trong cùng một tình huống

Giả sử chương trình tìm tên người dùng trong cache. Nếu cache không có dữ liệu, chương trình có thể tạo một tên mặc định hoặc tìm tiếp ở nguồn khác.

| Phương thức | Đầu vào dự phòng | Kết quả trả về | Khi nào dùng |
|---|---|---|---|
| `orElse("Guest")` | Một giá trị String | String | Cần lấy ngay giá trị cuối cùng |
| `orElseGet(this::createGuest)` | Supplier tạo String | String | Cần tạo giá trị cuối cùng một cách lazy |
| `or(this::findFromDatabase)` | Supplier tạo Optional | Optional<String> | Cần thử nguồn khác và tiếp tục giữ trạng thái có/không có giá trị |

Ví dụ:

~~~java
Optional<String> cachedName = findFromCache();

String direct = cachedName.orElse("Guest");

String lazy = cachedName.orElseGet(this::createGuest);

Optional<String> searched = cachedName.or(this::findFromDatabase);
~~~

Hai biến `direct` và `lazy` có kiểu String. Biến `searched` vẫn có kiểu Optional<String>. Nếu không tìm thấy dữ liệu ở cache và cơ sở dữ liệu, `searched` có thể rỗng để tầng gọi quyết định cách xử lý tiếp theo.

Không nên dùng `orElse("Guest")` quá sớm nếu tầng nghiệp vụ phía sau vẫn cần phân biệt “không tìm thấy người dùng” với “người dùng có tên Guest”. Việc chuyển Optional thành giá trị mặc định làm mất thông tin về nguồn gốc của kết quả.

## 6. Ví dụ Java chạy được: thời điểm gọi Supplier

Chương trình sau minh họa sự khác nhau giữa giá trị mặc định trực tiếp, Supplier tạo giá trị và Supplier trả về Optional.

~~~java
import java.util.Optional;

public class OptionalOrFallbackExample {
    private static String createDirectDefault() {
        System.out.println("evaluate direct default");
        return "default";
    }

    private static String createLazyDefault() {
        System.out.println("evaluate lazy default");
        return "lazy";
    }

    private static Optional<String> findFirstFallback() {
        System.out.println("lookup first fallback");
        return Optional.empty();
    }

    private static Optional<String> findSecondFallback() {
        System.out.println("lookup second fallback");
        return Optional.of("secondary");
    }

    private static Optional<String> findUnusedFallback() {
        System.out.println("lookup unused fallback");
        return Optional.of("unused");
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("cache");

        System.out.println("-- orElse: direct default --");
        String direct = present.orElse(createDirectDefault());
        System.out.println("result=" + direct);

        System.out.println("-- orElseGet: supplier default --");
        String lazy = present.orElseGet(
            OptionalOrFallbackExample::createLazyDefault
        );
        System.out.println("result=" + lazy);

        System.out.println("-- orElseGet on empty --");
        String emptyFallback = Optional.<String>empty()
            .orElseGet(OptionalOrFallbackExample::createLazyDefault);
        System.out.println("result=" + emptyFallback);

        System.out.println("-- or: Optional fallback chain --");
        Optional<String> searched = Optional.<String>empty()
            .or(OptionalOrFallbackExample::findFirstFallback)
            .or(OptionalOrFallbackExample::findSecondFallback);
        System.out.println("result=" + searched.orElse("none"));

        System.out.println("-- or: existing value --");
        Optional<String> unchanged = present.or(
            OptionalOrFallbackExample::findUnusedFallback
        );
        System.out.println("result=" + unchanged.orElse("none"));
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all OptionalOrFallbackExample.java
java OptionalOrFallbackExample
~~~

Kết quả stdout chính xác:

~~~text
-- orElse: direct default --
evaluate direct default
result=cache
-- orElseGet: supplier default --
result=cache
-- orElseGet on empty --
evaluate lazy default
result=lazy
-- or: Optional fallback chain --
lookup first fallback
lookup second fallback
result=secondary
-- or: existing value --
result=cache
~~~

Phân tích:

1. `orElse` gọi `createDirectDefault()` ngay khi đánh giá đối số, dù Optional đang chứa `cache`.
2. `orElseGet` không gọi `createLazyDefault()` khi Optional có giá trị.
3. Khi Optional rỗng, `orElseGet` mới gọi Supplier và trả về `lazy`.
4. Chuỗi `or` gọi nguồn dự phòng thứ nhất, nhận Optional rỗng, rồi mới gọi nguồn thứ hai. Nguồn thứ hai tìm thấy `secondary`.
5. Khi Optional ban đầu chứa `cache`, Supplier của `or` không được gọi và giá trị hiện có được giữ nguyên.

Dòng `lookup unused fallback` không xuất hiện trong stdout. Đây là bằng chứng rằng Supplier dự phòng của `or` không chạy khi Optional đã có giá trị.

## 7. Kết hợp với map, flatMap và orElseThrow

Các phương thức của Optional giải quyết những bước khác nhau:

- `map(mapper)`: biến đổi giá trị nếu Optional có giá trị; nếu rỗng, kết quả vẫn rỗng.
- `flatMap(mapper)`: gọi hàm có trả về Optional và tránh tạo Optional lồng nhau.
- `or(supplier)`: cung cấp một Optional thay thế khi Optional hiện tại rỗng.
- `orElse(value)` và `orElseGet(supplier)`: lấy ra giá trị T hoặc giá trị mặc định.
- `orElseThrow()`: lấy giá trị hoặc ném NoSuchElementException nếu rỗng.
- `orElseThrow(exceptionSupplier)`: lấy giá trị hoặc tạo và ném ngoại lệ do ứng dụng chỉ định.

Ví dụ kết hợp nhiều bước:

~~~java
User user = findInCache(userId)
    .or(() -> findInDatabase(userId))
    .orElseThrow(() ->
        new UserNotFoundException(userId)
    );
~~~

Đoạn mã tìm trong cache, sau đó mới tìm trong cơ sở dữ liệu. Nếu cả hai đều không có người dùng, chương trình ném ngoại lệ nghiệp vụ. Việc chuyển sang `User` chỉ diễn ra ở cuối chuỗi, tại điểm mà ứng dụng đã quyết định rằng không tìm thấy người dùng là một lỗi.

Nếu hàm ánh xạ đã trả về Optional, dùng flatMap để tránh Optional lồng nhau:

~~~java
Optional<Address> address = findUser(userId)
    .flatMap(User::primaryAddress);
~~~

Nếu cần một nguồn dự phòng cho địa chỉ:

~~~java
Optional<Address> address = findUser(userId)
    .flatMap(User::primaryAddress)
    .or(() -> findUser(userId).flatMap(User::backupAddress));
~~~

Trong ứng dụng thực tế, nếu cần tránh gọi lại `findUser(userId)`, hãy giữ Optional<User> trong một biến rồi sử dụng lại biến đó. Ví dụ trên tập trung vào cách kết hợp API.

## 8. Xử lý null và ngoại lệ trong Supplier

Các phương thức khác nhau có hợp đồng trả về khác nhau:

- `orElse(value)` có thể trả về null nếu Optional rỗng và đối số là null.
- `orElseGet(supplier)` trả về đúng kết quả Supplier khi Optional rỗng; nếu Supplier trả về null, kết quả cũng là null.
- `or(supplier)` yêu cầu Supplier trả về một Optional khác null. Muốn biểu diễn không có giá trị, trả về `Optional.empty()`.
- Nếu Supplier ném unchecked exception khi được gọi, ngoại lệ đó được truyền ra cho mã gọi.
- Nếu Optional có giá trị, Supplier của `orElseGet` hoặc `or` không được thực thi. Do đó, lỗi bên trong thân Supplier cũng không phát sinh trong trường hợp này.

Nên ưu tiên các API trả về Optional không null và dùng `Optional.ofNullable` ở ranh giới nhận dữ liệu nullable. Không trả null thay cho Optional vì điều đó làm mất lợi ích của hợp đồng kiểu.

## 9. Lỗi thường gặp

- **Dùng `orElse(expensiveCall())` và mong hàm chỉ chạy khi Optional rỗng:** sai. Đối số được đánh giá trước khi gọi phương thức.
- **Nghĩ `orElseGet` trả về Optional:** sai. Nó trả về giá trị T do Supplier tạo ra.
- **Dùng `or` với Supplier trả về giá trị T:** sai kiểu. Supplier của `or` phải trả về Optional.
- **Cho rằng `or` tự biến null thành Optional rỗng:** sai. Supplier trả về null làm phát sinh NullPointerException.
- **Dùng `orElse("Guest")` quá sớm:** có thể làm mất trạng thái không tìm thấy dữ liệu mà tầng nghiệp vụ cần biết.
- **Gọi nguồn dự phòng bằng cách tính trước Optional:** ví dụ `optional.orElse(findFromDatabase())` không hợp lệ về kiểu vì orElse cần T, và việc gọi hàm vẫn xảy ra ngay khi đánh giá đối số. Hãy dùng `or(() -> findFromDatabase())` nếu hàm trả về Optional.
- **Lồng nhiều Optional bằng map:** nếu mapper đã trả về Optional, dùng flatMap để tránh `Optional<Optional<T>>`.
- **Dùng Optional làm trường hoặc tham số ở mọi nơi:** Optional chủ yếu phù hợp làm kiểu trả về để thể hiện khả năng vắng mặt. Hãy theo quy ước API của dự án khi thiết kế trường, tham số và cấu trúc dữ liệu.

## 10. Cách chọn phương thức

- Cần một giá trị dự phòng đơn giản, đã có sẵn: dùng `orElse(value)`.
- Cần tính giá trị dự phòng chỉ khi thiếu dữ liệu: dùng `orElseGet(supplier)`.
- Cần thử một nguồn dữ liệu khác mà vẫn giữ trạng thái Optional: dùng `or(supplierOfOptional)`.
- Cần biến trường hợp không có dữ liệu thành lỗi nghiệp vụ: dùng `orElseThrow(...)`.
- Cần biến đổi giá trị đang có: dùng `map` hoặc `flatMap`.

Giữ Optional càng lâu càng tốt khi các tầng xử lý tiếp theo vẫn cần biết kết quả có tồn tại hay không. Chỉ chuyển sang giá trị trực tiếp tại nơi ứng dụng đã xác định rõ cách xử lý trường hợp rỗng.

## 11. Tài liệu tham khảo chính thức

- [Optional — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): hợp đồng của `or`, `orElse`, `orElseGet`, `map`, `flatMap` và `orElseThrow`.
- [Supplier — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Supplier.html): giao diện hàm dùng để cung cấp giá trị theo yêu cầu.
- [Java Language Specification — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.7): thứ tự đánh giá biểu thức và đối số lời gọi phương thức.