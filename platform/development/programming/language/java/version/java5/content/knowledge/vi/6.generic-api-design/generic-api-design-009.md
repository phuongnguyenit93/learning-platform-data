# Tài liệu hóa tham số kiểu và giới hạn bằng Javadoc

## 1. Chữ ký cho biết ràng buộc kiểu; Javadoc giải thích hợp đồng sử dụng

Một chữ ký như sau đã cung cấp nhiều thông tin cho trình biên dịch:

```java
public static <T extends Comparable<? super T>>
T firstMaximum(java.util.List<? extends T> values)
```

Đây chỉ là phần đầu của khai báo phương thức minh họa, chưa có thân để biên dịch độc lập. Nó cho biết kiểu `T` cần đáp ứng khả năng so sánh, danh sách cung cấp các phần tử phù hợp với `T` và kết quả được trả dưới kiểu `T`.

Nhưng người dùng API vẫn cần biết:

- So sánh theo thứ tự tự nhiên hay theo một quy tắc khác?
- Danh sách rỗng hoặc phần tử `null` được xử lý thế nào?
- Khi nhiều phần tử cùng lớn nhất, trả về phần tử nào?
- Phương thức có sửa danh sách, tạo bản sao hay trả lại tham chiếu đang có?

Đó là phần hợp đồng cần viết trong **Javadoc**. Một tài liệu tốt vừa giải thích vai trò của tham số kiểu, vừa mô tả hành vi mà chữ ký không biểu đạt được.

Bài này dùng cú pháp chú thích `/** ... */`, vẫn được hỗ trợ trong JDK hiện hành, để các ví dụ chạy được từ Java 17 trở lên. Không cần đổi API sang một cách triển khai khác chỉ để có nhiều thẻ tài liệu.

## 2. Thẻ @param cho tham số kiểu

Với một phương thức tự khai báo `<T>`, viết thẻ theo dạng:

```java
/**
 * Trả về giá trị được cung cấp.
 *
 * @param <T> kiểu của giá trị đầu vào và kết quả
 * @param value giá trị cần trả lại; có thể là {@code null}
 * @return chính tham chiếu {@code value}
 */
public static <T> T keep(T value) {
    return value;
}
```

Đây là khai báo đặt trong một lớp. Cần phân biệt:

| Thẻ | Đang mô tả gì? |
| --- | --- |
| `@param <T>` | Tham số **kiểu** có tên `T` |
| `@param value` | Tham số **giá trị** có tên `value` |
| `@return` | Kết quả và quan hệ với dữ liệu đầu vào |

Cặp dấu `<` và `>` trong `@param <T>` là một phần cú pháp của thẻ dành cho tham số kiểu, không phải phần trang trí. Viết `@param T` ở đây sẽ được hiểu là mô tả một tham số giá trị tên `T`, không đúng khai báo đang có.

Tên trong thẻ phải khớp tên thật. Nếu đổi `<T>` thành `<E>`, cập nhật cả `@param <E>` và các mô tả liên quan. Không viết `@param <String>` để mô tả đối số kiểu mà một bên gọi cụ thể sử dụng; tài liệu của khai báo phải mô tả tham số kiểu do chính khai báo đó sở hữu.

## 3. Giải thích vai trò, không chỉ nhắc lại tên

Mô tả `@param <T> kiểu T` không giúp người dùng hiểu API. Mô tả nên trả lời “T đại diện cho điều gì và nó liên kết những vị trí nào?”.

Ví dụ với `<K, V>` trong một API lưu ánh xạ:

```java
/**
 * Tạo một ánh xạ chứa đúng một cặp khóa và giá trị.
 *
 * @param <K> kiểu khóa của ánh xạ kết quả
 * @param <V> kiểu giá trị của ánh xạ kết quả
 * @param key khóa cần đưa vào; có thể là {@code null}
 * @param value giá trị cần đưa vào; có thể là {@code null}
 * @return một map mới có thể thay đổi, giữ các tham chiếu đã truyền vào
 */
public static <K, V> java.util.Map<K, V> mapping(K key, V value) {
    java.util.Map<K, V> result = new java.util.LinkedHashMap<>();
    result.put(key, value);
    return result;
}
```

Đoạn này mô tả rõ hai tham số kiểu độc lập, chính sách `null`, quyền thay đổi của map và việc các phần tử không được sao chép sâu. Những thông tin đó có ích hơn việc chỉ chép lại `Map<K, V>` vào phần văn xuôi.

Các mô tả phải phù hợp với implementation. Nếu đổi phần thân sang `Map.of`, cần cập nhật hợp đồng vì map kết quả không cho sửa và không chấp nhận khóa/giá trị `null`. Không giữ nguyên Javadoc rồi coi đây là thay đổi triển khai vô hại.

## 4. Mô tả giới hạn kiểu bằng ý nghĩa của thuật toán

Trong `<T extends Comparable<? super T>>`, không chỉ viết “T extends Comparable”. Cần nói kiểu phần tử được so sánh theo thứ tự tự nhiên và quan hệ `Comparable` phải phù hợp với kiểu mà thuật toán nhận.

Một mô tả thích hợp:

```java
/**
 * Chọn giá trị đứng trước theo thứ tự tự nhiên; giữ first khi so sánh bằng nhau.
 *
 * @param <T> kiểu có thứ tự tự nhiên, cho phép so sánh với các giá trị
 *            kiểu {@code T} thông qua {@link Comparable}
 * @param first giá trị đầu tiên, phải khác null
 * @param second giá trị thứ hai, phải khác null
 * @return một trong hai tham chiếu đầu vào
 * @throws NullPointerException nếu một đối số là null
 */
public static <T extends Comparable<? super T>> T earlier(T first, T second) {
    java.util.Objects.requireNonNull(first, "first");
    java.util.Objects.requireNonNull(second, "second");
    return first.compareTo(second) <= 0 ? first : second;
}
```

`Comparable<? super T>` cho phép thao tác so sánh được cung cấp cho `T` hoặc một kiểu cha phù hợp. Không cần diễn giải toàn bộ thuật toán suy luận kiểu trong Javadoc của mỗi phương thức; hãy giải thích khả năng mà thuật toán dựa vào và hành vi liên quan.

Với nhiều giới hạn, chẳng hạn `<T extends Base & Runnable>`, tài liệu nên giải thích vì sao thuật toán cần cả dữ liệu từ lớp cơ sở lẫn khả năng chạy, thay vì mô tả `T` như một kiểu chỉ cần đáp ứng một trong hai. Dấu `&` biểu thị các yêu cầu đồng thời.

Không hứa những điều giới hạn không bảo đảm: `extends Comparable` không tự cấm `null`, không tự làm đối tượng bất biến và không tự làm một phương thức an toàn đa luồng.

## 5. Wildcard không có thẻ @param kiểu riêng

Với tham số `List<? extends T> values`:

- `@param <T>` mô tả tham số kiểu có tên `T` do phương thức khai báo.
- `@param values` mô tả danh sách nguồn, dữ liệu được chấp nhận và các điều kiện của nó.
- Không tạo thẻ `@param <? extends T>`; wildcard ấy không phải một tham số kiểu có tên được khai báo.

Nếu phương thức chỉ nhận `List<?>` mà không tự khai báo tham số kiểu, nó không cần thẻ `@param <T>` tưởng tượng. Tài liệu phải bám vào các thành phần thực sự tồn tại trong chữ ký.

Một chữ ký dùng `? extends T` cũng không chứng minh phần thân không sửa danh sách: có những thao tác như xóa hoặc `clear` vẫn phù hợp về kiểu. Nếu API hứa không thay đổi nguồn, ghi rõ điều đó và xác minh phần thân đúng với lời hứa.

## 6. Chương trình đầy đủ có hợp đồng Javadoc

Lưu toàn bộ mã sau bằng UTF-8 thành **`GenericDocsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

/**
 * Minh họa hợp đồng Javadoc cho phương thức generic tìm giá trị lớn nhất.
 */
public final class GenericDocsDemo {
    private GenericDocsDemo() {
    }

    /**
     * Trả về phần tử lớn nhất đầu tiên theo thứ tự tự nhiên.
     *
     * <p>Phương thức không thay đổi danh sách đầu vào. Khi nhiều phần tử
     * so sánh bằng nhau, phần tử gặp trước trong thứ tự duyệt được trả về.
     * Kết quả là một tham chiếu có sẵn trong danh sách, không phải bản sao.</p>
     *
     * <p>Ví dụ:</p>
     * <pre>{@code
     * Integer best = GenericDocsDemo.firstMaximum(List.of(4, 9, 2));
     * }</pre>
     *
     * @param <T> kiểu phần tử có thứ tự tự nhiên, cho phép so sánh với
     *            các giá trị kiểu T thông qua Comparable
     * @param values danh sách khác null, không rỗng và không chứa null
     * @return phần tử lớn nhất đầu tiên; luôn khác null
     * @throws NullPointerException nếu values là null hoặc chứa phần tử null
     * @throws IllegalArgumentException nếu values rỗng
     */
    public static <T extends Comparable<? super T>>
    T firstMaximum(List<? extends T> values) {
        Objects.requireNonNull(values, "values");
        Iterator<? extends T> iterator = values.iterator();
        if (!iterator.hasNext()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        T best = Objects.requireNonNull(iterator.next(), "element");
        while (iterator.hasNext()) {
            T candidate = Objects.requireNonNull(iterator.next(), "element");
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    /**
     * Chạy các ví dụ hợp lệ và các điều kiện bị từ chối.
     *
     * @param args đối số dòng lệnh; không sử dụng
     */
    public static void main(String[] args) {
        Integer max = firstMaximum(List.of(4, 9, 2));
        String word = firstMaximum(List.of("fig", "pear", "apple"));
        System.out.println("max=" + max);
        System.out.println("word=" + word);

        try {
            firstMaximum(List.<Integer>of());
        } catch (IllegalArgumentException ex) {
            System.out.println("empty rejected");
        }

        try {
            firstMaximum(Arrays.asList(1, null));
        } catch (NullPointerException ex) {
            System.out.println("null element rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all GenericDocsDemo.java
java GenericDocsDemo
```

Stdout chính xác:

```text
max=9
word=pear
empty rejected
null element rejected
```

Implementation duyệt theo thứ tự iterator của danh sách, chỉ thay giá trị tốt nhất khi kết quả so sánh lớn hơn `0`, vì vậy giữ phần tử đầu tiên khi có nhiều cực đại so sánh bằng nhau. Nó kiểm tra mọi phần tử đã duyệt bằng `requireNonNull` và không gọi các thao tác sửa danh sách.

Cụm “so sánh bằng nhau” ở đây dựa vào `compareTo` trả về `0`, không tự đồng nghĩa với hai đối tượng có cùng tham chiếu hoặc `equals` trả về `true`. Đây là một chi tiết hợp đồng có giá trị khi làm việc với generic có giới hạn so sánh.

Ví dụ dùng `Arrays.asList(1, null)` để tạo được một đầu vào có phần tử `null` cho phép kiểm chứng điều kiện từ chối. Dùng `List.of(1, null)` sẽ ném ngoại lệ ngay lúc tạo danh sách, trước khi phương thức đang được kiểm thử nhận dữ liệu.

## 7. Tài liệu tham số kiểu của lớp đặt ở chú thích lớp

Một lớp generic sở hữu tham số kiểu ở mức lớp. Ví dụ độc lập, lưu thành **`ValueBox.java`** nếu muốn tạo tài liệu cho nó:

```java
import java.util.Objects;

/**
 * Giữ cố định một tham chiếu giá trị khác null.
 *
 * <p>Lớp không sao chép đối tượng giá trị và không ngăn đối tượng đó
 * thay đổi trạng thái nếu kiểu T cho phép.</p>
 *
 * @param <T> kiểu của giá trị được giữ
 */
public final class ValueBox<T> {
    private final T value;

    /**
     * Tạo hộp giữ giá trị được cung cấp.
     *
     * @param value giá trị cần giữ; phải khác null
     * @throws NullPointerException nếu value là null
     */
    public ValueBox(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    /**
     * Trả lại tham chiếu được giữ trong hộp.
     *
     * @return chính tham chiếu nhận từ constructor; không phải bản sao
     */
    public T get() {
        return value;
    }
}
```

`@param <T>` đặt ở lớp `ValueBox<T>`. Phương thức `get()` không tự khai báo tham số kiểu mới nên không thêm `@param <T>` cho phương thức ấy. Nó sử dụng `T` của lớp.

Nếu một phương thức khác trong lớp tự khai báo `<R>`, mô tả `@param <R>` tại chính phương thức đó. Đừng gộp mọi biến kiểu của các phạm vi khác nhau vào một chú thích chung.

## 8. Viết ký hiệu generic an toàn trong nội dung Javadoc

Trong chú thích truyền thống, nội dung thường được xử lý như HTML. Viết trực tiếp `List<T>` trong văn xuôi có thể làm dấu ngoặc nhọn bị hiểu như thẻ HTML. Dùng inline tag:

```java
/**
 * Đọc dữ liệu từ {@code List<? extends T>}.
 * So sánh bằng {@link Comparable} khi hợp đồng kiểu cho phép.
 */
```

- `{@code ...}` hiển thị đoạn mã và xử lý các ký tự như `<`, `>` mà không coi chúng là markup HTML trong đoạn đó.
- `{@link ...}` liên kết tới một khai báo Java có thể phân giải; dùng nó khi một đích API cụ thể thật sự giúp người đọc.
- Với ví dụ nhiều dòng, có thể dùng `<pre>{@code ...}</pre>` như chương trình trên.
- Đừng thay `@param <T>` bằng `@param {@code T}`; phần tên tham số của block tag cần đúng cú pháp riêng của nó.

Nếu cần viết dấu `&` như văn bản HTML ở ngoài `{@code ...}`, dùng entity phù hợp như `&amp;`. Đưa một chữ ký chứa nhiều giới hạn vào `{@code ...}` thường dễ đọc và ít lỗi hơn tự xử lý từng ký tự.

Không đặt một Javadoc sau khi khai báo đã bắt đầu hoặc chỉ dùng `/* ... */` rồi mong công cụ nhận nó như tài liệu API. Chú thích tài liệu cần gắn ngay trước khai báo mà nó mô tả, trước cả annotation của khai báo nếu có.

## 9. Sinh tài liệu và kiểm tra bằng DocLint

Sau khi lưu hai tệp ví dụ, có thể tạo tài liệu HTML trong thư mục `docs`:

```shell
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror --no-platform-links -d docs GenericDocsDemo.java ValueBox.java
```

`--no-platform-links` trong ví dụ bỏ liên kết tự động tới tài liệu nền tảng Java bên ngoài; các khai báo vẫn được kiểm tra từ JDK. Nếu muốn tài liệu phát hành có liên kết API nền tảng, cấu hình việc liên kết phù hợp với JDK và môi trường xây dựng thực tế.

Các điểm chính của lệnh:

| Tùy chọn | Mục đích |
| --- | --- |
| `--release 17` | Kiểm tra ví dụ theo mức API/ngôn ngữ Java 17 |
| `-encoding UTF-8` | Đọc mã nguồn có dấu tiếng Việt đúng encoding |
| `-docencoding UTF-8`, `-charset UTF-8` | Ghi và khai báo encoding cho HTML kết quả |
| `-Xdoclint:all` | Kiểm tra các nhóm lỗi tài liệu mà DocLint hỗ trợ |
| `-Werror` | Khi có warning, coi lần chạy là không đạt |
| `-d docs` | Ghi đầu ra HTML vào thư mục được chỉ định |

Mở `docs/index.html` để kiểm tra trang tạo ra, các mục type parameters, parameters, returns và throws. Tài liệu hiện đúng markup chưa có nghĩa nội dung đúng hợp đồng.

DocLint có thể phát hiện nhiều lỗi cú pháp, tham chiếu, cấu trúc HTML hoặc thẻ không phù hợp. Nó **không chứng minh** implementation thật sự không sửa nguồn, trả phần tử đầu tiên khi hòa, hoặc từ chối đúng mọi tình huống `null`. Những lời hứa ấy cần kiểm tra mã và bằng chứng chạy phù hợp.

Không tắt DocLint hoặc xóa thẻ chỉ để làm mất cảnh báo khi nguyên nhân là tài liệu không khớp khai báo.

## 10. Những lỗi thường gặp khi viết tài liệu API generic

- **Chỉ mô tả T là “một kiểu bất kỳ”:** bỏ mất vai trò như kiểu phần tử, khóa, giá trị hoặc quan hệ đầu vào–đầu ra.
- **Lặp lại bound nhưng thiếu hành vi:** ghi `extends Comparable` mà không nói thứ tự so sánh, phần tử hòa hoặc chính sách dữ liệu rỗng.
- **Thẻ sai phạm vi:** viết `@param <T>` ở một phương thức chỉ dùng `T` của lớp nhưng không tự khai báo nó.
- **Tưởng wildcard là tên tham số:** tạo thẻ `@param <?>` hoặc `@param <? super T>` thay vì mô tả tham số giá trị liên quan.
- **Hứa bất biến sâu chỉ vì có final/generic:** `ValueBox<T>` giữ cố định tham chiếu nhưng không ngăn đối tượng `T` thay đổi.
- **Mô tả null không khớp mã:** nói “không chấp nhận null” nhưng không rõ danh sách null, phần tử null hay cả hai.
- **Ghi ví dụ không chạy hoặc stdout không đúng:** chú thích ví dụ vẫn cần được biên dịch/chạy như mã khác khi dùng làm bằng chứng.

Với một API đã phát hành, cập nhật Javadoc cùng thay đổi hợp đồng. Đừng ghi `@since 5` chỉ vì dùng generic có từ Java 5; `@since` của API nên chỉ phiên bản sản phẩm/thư viện mà khai báo đó được giới thiệu, theo quy ước của dự án.

## 11. Tự thực hành

1. Đổi tên tham số kiểu của `firstMaximum` từ `T` sang `E`, cập nhật chữ ký và Javadoc rồi chạy DocLint.
2. Viết thêm mô tả rõ cho một phương thức dùng `<K, V>`: vai trò của mỗi kiểu, chính sách khóa/giá trị `null` và quyền thay đổi của kết quả.
3. Tạo hai đối tượng khác tham chiếu nhưng so sánh bằng nhau rồi kiểm tra `firstMaximum` trả đúng đối tượng xuất hiện trước.
4. Kiểm tra danh sách đầu vào còn nguyên sau lời gọi, và kiểm tra trường hợp chính tham chiếu danh sách là `null` chứ không chỉ phần tử null.
5. Cố tình đổi `@param <T>` thành `@param T` trên phương thức mẫu để quan sát chẩn đoán; khôi phục đúng cú pháp trước khi tạo tài liệu cuối cùng.

Tài liệu generic cần giúp người dùng hiểu không chỉ “kiểu nào biên dịch được” mà còn “lời gọi có hành vi gì”. Gắn mô tả tham số kiểu với các điều kiện dữ liệu, kết quả, ngoại lệ và quyền sở hữu sẽ làm hợp đồng API cụ thể và kiểm chứng được.

## Tài liệu đối chiếu

- [JavaDoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): block tag, inline tag và cú pháp chú thích được standard doclet hỗ trợ.
- [The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): tùy chọn tạo tài liệu, DocLint và kiểm tra cảnh báo.
- [Collections.max — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#max(java.util.Collection)): đối chiếu cách thư viện chuẩn tài liệu hóa giới hạn so sánh của một API generic.
