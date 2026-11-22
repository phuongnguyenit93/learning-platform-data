# Mục đích và đặc điểm biểu diễn của EnumSet

## 1. Khái niệm: tập hợp các hằng của cùng một kiểu enum

`EnumSet` là một triển khai `Set` chuyên dụng cho các phần tử thuộc cùng một kiểu enum.

Ví dụ:

```java
// Khai báo minh họa.
enum Capability {
    READ,
    WRITE,
    DELETE,
    EXECUTE
}
```

Một đối tượng có thể hỗ trợ một nhóm khả năng như đọc và xóa:

```java
// Minh họa trong một phương thức; cần import java.util.EnumSet.
EnumSet<Capability> selected =
        EnumSet.of(Capability.READ, Capability.DELETE);
```

Ý nghĩa là một **tập con** của tập các hằng `Capability`, không phải một danh sách theo số lần xuất hiện.

Các tính chất của `Set` vẫn áp dụng:

- Một hằng chỉ có thể hiện diện hoặc không hiện diện; không có bản sao trùng.
- Thêm lại phần tử đã có không tăng kích thước tập.
- Thành viên được nhận diện theo hằng enum tương ứng.

`EnumSet` phù hợp với các nhóm chế độ, lựa chọn, trạng thái được phép hoặc khả năng mà toàn bộ miền giá trị đã được mô hình hóa bằng một enum.

Các nguyên tắc và API trong bài vẫn được dùng trên Java hiện đại. Chương trình thực hành chạy trên Java 17 trở lên.

## 2. Vì sao dùng một collection chuyên dụng?

Một tập tổng quát như `HashSet` có thể chứa hằng enum. Tuy nhiên, với enum, thư viện biết trước một tập hữu hạn các hằng thuộc cùng một kiểu.

Điều đó cho phép `EnumSet` dùng biểu diễn chuyên biệt: **vector bit** (bit vector). Thay vì lưu một bản ghi băm riêng theo cách của tập tổng quát, nó theo dõi sự có mặt của các hằng bằng các vị trí bit tương ứng.

Người viết mã vẫn làm việc qua API collection có kiểu:

```java
// Minh họa trong một phương thức.
selected.add(Capability.WRITE);
boolean canRead = selected.contains(Capability.READ);
selected.remove(Capability.DELETE);
```

Không cần tự đặt các con số cho từng hằng hoặc tự thao tác mặt nạ bit ở mã sử dụng. Quan hệ giữa hằng enum và bit được collection quản lý.

Lợi ích chính là kết hợp:

- Ý nghĩa phần tử rõ ràng qua enum.
- Kiểm tra kiểu khi biên dịch.
- Biểu diễn nhỏ gọn phù hợp với miền giá trị hữu hạn.
- Các thao tác tập hợp như hợp, giao và phần bù.

Không chọn `EnumSet` cho một tập các chuỗi tùy ý hoặc các giá trị được bổ sung động ngoài enum; đó là một bài toán miền dữ liệu khác.

## 3. Mô hình biểu diễn: mỗi hằng tương ứng một vị trí

Với `Capability` ở đầu bài, có thể hình dung:

| Hằng | Vị trí khai báo bắt đầu từ 0 | Bit có bật khi tập chứa hằng? |
| --- | --- | --- |
| `READ` | 0 | Có nếu chứa `READ` |
| `WRITE` | 1 | Có nếu chứa `WRITE` |
| `DELETE` | 2 | Có nếu chứa `DELETE` |
| `EXECUTE` | 3 | Có nếu chứa `EXECUTE` |

Một cách vẽ theo bit cao đến bit thấp:

```text
Hằng:       EXECUTE DELETE WRITE READ
Tập rỗng:      0      0     0     0
READ,DELETE:   0      1     0     1
Tất cả:        1      1     1     1
```

Hình vẽ minh họa ý tưởng thành viên, không phải một API để lấy số nguyên nội bộ hoặc một định dạng lưu trữ được ứng dụng nên phụ thuộc.

Từ mô hình này:

- Thêm phần tử tương ứng với đánh dấu có mặt.
- Xóa phần tử tương ứng với bỏ đánh dấu.
- Kiểm tra `contains` tương ứng với kiểm tra vị trí.
- Hợp hai tập tương ứng với kết hợp các vị trí có mặt.
- Giao giữ các vị trí cùng có mặt.
- Phần bù xét các hằng còn thiếu **trong đúng miền enum**, không bao gồm những giá trị bên ngoài.

Một bit không thể đếm hai lần xuất hiện, nên biểu diễn này cũng khớp tự nhiên với ngữ nghĩa không trùng lặp của `Set`.

## 4. Một long hay nhiều long: chi tiết triển khai, không phải giới hạn API

Trong mã nguồn OpenJDK 21 được đối chiếu:

- Với kiểu enum có tối đa 64 hằng, triển khai nội bộ `RegularEnumSet` dùng một trường `long` để theo dõi thành viên.
- Với kiểu enum có hơn 64 hằng, `JumboEnumSet` dùng một mảng `long`.

Điều cần nhìn là **tổng số hằng của kiểu enum**, không chỉ số phần tử đang có trong tập. Một tập hiện chỉ chứa một hằng của enum có hơn 64 hằng vẫn cần biểu diễn phù hợp với miền enum lớn ấy.

Các tên lớp nội bộ trên giúp giải thích cách làm của phiên bản triển khai đã nêu. Mã ứng dụng không nên:

- Tự khởi tạo các lớp nội bộ ấy.
- Ép kiểu theo tên lớp triển khai.
- Dựa vào `getClass().getSimpleName()` để quyết định logic.
- Cho rằng mọi `EnumSet` luôn có đúng một từ máy.
- Cho rằng `EnumSet` chỉ hỗ trợ tối đa 64 giá trị.

Hợp đồng sử dụng nằm ở `EnumSet`; thư viện tự chọn biểu diễn phù hợp.

Một trường `long` cũng không có nghĩa toàn bộ đối tượng tập chỉ chiếm 8 byte. Còn có cấu trúc đối tượng, thông tin kiểu và các thành phần liên quan; kích thước thực tế phụ thuộc JVM và triển khai.

## 5. Hiệu quả và giới hạn của việc suy luận từ vector bit

Biểu diễn vector bit làm các thao tác thành viên có thể được triển khai trực tiếp trên vị trí của hằng. Trong triển khai đã nêu, các thao tác cơ bản như thêm, xóa hoặc kiểm tra một hằng không cần tìm một phần tử bằng cách quét toàn bộ tập.

Các thao tác hàng loạt giữa hai `EnumSet` cùng kiểu có thể tận dụng phép toán trên các nhóm bit. Với miền lớn dùng nhiều từ `long`, một thao tác hàng loạt có thể cần xử lý nhiều từ; không nên nói mọi phép toán đều luôn chỉ là một lệnh hoặc luôn có chi phí không phụ thuộc kích thước miền.

So sánh định tính:

| Tiêu chí | EnumSet | Một tập tổng quát như HashSet |
| --- | --- | --- |
| Miền phần tử | Một kiểu enum | Các đối tượng phù hợp với kiểu khai báo |
| Biểu diễn chuyên dụng | Vector bit | Cấu trúc băm theo triển khai |
| Phần tử trùng | Không | Không |
| Thứ tự duyệt được bảo đảm ở đây | Thứ tự khai báo hằng enum | HashSet không bảo đảm thứ tự |
| Trường hợp phù hợp | Tập con của một miền enum hữu hạn | Tập phần tử tổng quát |

Không suy ra một hệ số nhanh hơn hoặc một số byte tiết kiệm cố định cho mọi ứng dụng. `EnumSet` có lợi thế cấu trúc rõ ràng cho bài toán này; nếu hiệu năng là yêu cầu chính, đo trên dữ liệu và môi trường cụ thể.

## 6. Thứ tự duyệt: theo khai báo, không theo lần thêm

```java
// Minh họa trong một phương thức.
EnumSet<Capability> selected =
        EnumSet.of(Capability.DELETE, Capability.READ);

System.out.println(selected);
```

Kết quả:

```text
[READ, DELETE]
```

Dù `DELETE` được truyền trước, tập duyệt theo thứ tự tự nhiên của enum, tức thứ tự các hằng được khai báo.

Đó không phải thứ tự chữ cái và cũng không phải thứ tự chèn. Thay đổi thứ tự khai báo enum có thể thay đổi thứ tự duyệt của tập.

Ngữ nghĩa bằng nhau của tập vẫn dựa trên các thành viên, không phải một lịch sử thêm/xóa. Thứ tự duyệt là một bảo đảm bổ sung hữu ích để in hoặc trình bày ổn định theo miền enum.

## 7. Kiểu enum được giữ cả khi tập rỗng

`EnumSet` cần biết kiểu enum để xác định miền các hằng và cách biểu diễn thành viên.

Vì vậy, tạo tập rỗng thường dùng:

```java
// Minh họa trong một phương thức.
EnumSet<Capability> empty = EnumSet.noneOf(Capability.class);
```

`empty` có kích thước `0` nhưng vẫn là tập của `Capability`. Biết miền không có nghĩa đang chứa toàn bộ miền.

Những lựa chọn thường dùng khác:

```java
// Minh họa trong một phương thức.
EnumSet<Capability> all = EnumSet.allOf(Capability.class);
EnumSet<Capability> chosen = EnumSet.of(Capability.READ);
EnumSet<Capability> copied = EnumSet.copyOf(chosen);
```

`EnumSet` là lớp trừu tượng được sử dụng qua các factory; không tạo bằng `new EnumSet<>()`.

### Vì sao copyOf một collection rỗng có thể thất bại?

```java
// Minh họa lỗi runtime; cần import java.util.List.
EnumSet<Capability> result =
        EnumSet.copyOf(List.<Capability>of());
```

Collection đầu vào rỗng và không phải một `EnumSet`, nên factory không có phần tử hoặc metadata enum-set để xác định kiểu enum ở runtime. Kết quả là `IllegalArgumentException`.

Kiểu generic `Capability` được ghi ở mã nguồn không tự truyền một `Class<Capability>` cho phương thức này.

Ngược lại, sao chép một `EnumSet` rỗng có thể giữ được thông tin kiểu đã có:

```java
// Minh họa hợp lệ.
EnumSet<Capability> empty = EnumSet.noneOf(Capability.class);
EnumSet<Capability> copiedEmpty = EnumSet.copyOf(empty);
```

Sự khác nhau này phản ánh yêu cầu biểu diễn: một tập không có phần tử vẫn cần biết miền enum của nó.

## 8. Không trộn kiểu enum và không thêm null

Một `EnumSet<Capability>` nhận các hằng `Capability`. Truyền một hằng của enum khác vào `add` sẽ không phù hợp với hợp đồng generic.

`null` không phải một hằng của enum:

```java
// Minh họa lỗi runtime.
selected.add(null);
```

Thao tác thêm `null` ném `NullPointerException`.

Tuy nhiên, các thao tác kiểm tra hoặc loại bỏ `null` được xử lý như không có phần tử đó: `contains(null)` và `remove(null)` trả về `false`. Không suy ra rằng vì kiểm tra `null` hợp lệ thì thêm nó cũng hợp lệ.

Một ứng dụng cần trạng thái “không có lựa chọn” thường có thể dùng tập rỗng. Nếu cần một trạng thái nghiệp vụ riêng, hãy mô hình hóa tường minh; không đưa `null` vào tập để giả làm một hằng enum.

## 9. Khả năng sửa đổi, sao chép và chia sẻ

Các `EnumSet` thông thường được tạo bởi factory hỗ trợ thêm/xóa theo hợp đồng của tập.

`EnumSet.copyOf(existingEnumSet)` tạo một tập thành viên riêng. Thêm hoặc xóa ở bản sao không tự sửa tập gốc:

```java
// Minh họa trong một phương thức.
EnumSet<Capability> original = EnumSet.of(Capability.READ);
EnumSet<Capability> copy = EnumSet.copyOf(original);
copy.add(Capability.WRITE);
```

Sau đó, tập gốc vẫn chỉ chứa `READ`. Các thành viên là các hằng enum đã có, không có chuyện tạo các hằng enum mới cho bản sao.

Nếu chỉ cần công khai giao diện tập hợp, có thể dùng kiểu `Set<Capability>` ở ranh giới API mà đối tượng bên dưới vẫn là `EnumSet`. Cách khai báo biến không thay đổi biểu diễn runtime.

`EnumSet` không tự đồng bộ cho truy cập nhiều luồng. Iterator của nó có tính nhất quán yếu (weakly consistent), không ném `ConcurrentModificationException` và có thể thấy hoặc không thấy thay đổi xảy ra trong lúc duyệt. Điều đó không biến việc đọc/ghi đồng thời tùy ý thành một giao thức an toàn; nếu cần chia sẻ có sửa đổi, phải thiết kế cơ chế phối hợp phù hợp.

## 10. Đừng dùng vị trí bit nội bộ làm định dạng dữ liệu bên ngoài

Vị trí khai báo của một hằng có thể lấy qua `ordinal()`, nhưng mục đích của vị trí trong cấu trúc chuyên dụng không làm nó thành định danh ổn định cho dữ liệu ứng dụng.

Khi thêm hoặc đổi thứ tự hằng enum:

- Cách hình dung vị trí bit có thể thay đổi.
- Thứ tự duyệt có thể thay đổi.
- `allOf` và phần bù trên phiên bản enum mới có thể có thành viên mới.

Không tự ghi số bit nội bộ hoặc `ordinal` ra cơ sở dữ liệu/giao thức rồi coi nó là hợp đồng bền vững. Nếu cần trao đổi lâu dài, thiết kế các định danh và quy tắc tương thích rõ ràng, độc lập với biểu diễn riêng của collection.

Cũng không dùng `allOf` hoặc phần bù trong một quy tắc cần cố định danh sách thành viên mà không xét tác động khi enum được mở rộng.

## 11. Chương trình đầy đủ

Lưu vào `EnumSetRepresentationDemo.java`:

```java
import java.util.EnumSet;
import java.util.List;

public class EnumSetRepresentationDemo {
    enum Capability {
        READ,
        WRITE,
        DELETE,
        EXECUTE
    }

    public static void main(String[] args) {
        EnumSet<Capability> selected =
                EnumSet.of(Capability.DELETE, Capability.READ);
        System.out.println(selected);
        System.out.println("duplicateAdded="
                + selected.add(Capability.READ));

        EnumSet<Capability> empty =
                EnumSet.noneOf(Capability.class);
        System.out.println(empty);

        EnumSet<Capability> all =
                EnumSet.allOf(Capability.class);
        System.out.println(all);

        EnumSet<Capability> copy = EnumSet.copyOf(selected);
        copy.add(Capability.WRITE);
        System.out.println(copy);
        System.out.println(selected);

        EnumSet<Capability> intersection = EnumSet.copyOf(copy);
        intersection.retainAll(
                EnumSet.of(Capability.READ, Capability.EXECUTE));
        System.out.println(intersection);

        EnumSet<Capability> missing = EnumSet.complementOf(selected);
        System.out.println(missing);

        System.out.println("containsNull=" + selected.contains(null));
        try {
            selected.add(null);
        } catch (NullPointerException ex) {
            System.out.println("null rejected");
        }

        try {
            EnumSet.copyOf(List.<Capability>of());
        } catch (IllegalArgumentException ex) {
            System.out.println("empty collection needs enum type");
        }

        for (Capability capability : selected) {
            System.out.println("seen=" + capability);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumSetRepresentationDemo.java
java EnumSetRepresentationDemo
```

Stdout chính xác:

```text
[READ, DELETE]
duplicateAdded=false
[]
[READ, WRITE, DELETE, EXECUTE]
[READ, WRITE, DELETE]
[READ, DELETE]
[READ]
[WRITE, EXECUTE]
containsNull=false
null rejected
empty collection needs enum type
seen=READ
seen=DELETE
```

Các điểm cần quan sát:

1. Thứ tự truyền vào factory không thay thứ tự duyệt theo khai báo.
2. Thêm lại `READ` không tạo phần tử thứ hai.
3. Tập rỗng và toàn bộ miền có cùng kiểu enum nhưng các thành viên khác nhau.
4. Bản sao có thể được sửa độc lập về thành viên.
5. Giao và phần bù làm việc trên tập hằng, không cần thao tác số bit ở mã sử dụng.
6. Kiểm tra `null` khác với thêm `null`.
7. Collection rỗng thông thường không cung cấp đủ kiểu enum cho `copyOf`.
8. For-each quan sát cùng thứ tự tự nhiên đã nêu.

Chương trình không in tên lớp triển khai nội bộ và không truy cập các bit bằng reflection. Những chi tiết đó không cần cho việc sử dụng API đúng.

## 12. Quan hệ với EnumMap và cách chọn

Trong nhóm collection chuyên dụng cho enum:

- `EnumSet<E>` mô tả một tập các hằng `E`: có hay không có từng thành viên.
- `EnumMap<E, V>` ánh xạ mỗi khóa enum sang một giá trị `V`.

Nếu cần một nhóm khả năng đang bật, `EnumSet` diễn đạt đúng hơn một map tự lưu `true/false` cho từng khóa. Nếu cần mỗi chế độ gắn với một cấu hình hoặc kết quả riêng, đó là nhu cầu của map, không phải chỉ một bit thành viên.

Không chọn chỉ vì tên hai lớp cùng có chữ “Enum”. Trước hết xác định mô hình cần lưu là tập thành viên hay ánh xạ khóa–giá trị.

Bài tập:

1. Tạo enum gồm bốn chế độ và vẽ vector bit khái niệm cho một tập chứa hai chế độ.
2. Thêm các hằng theo thứ tự ngược khai báo rồi quan sát thứ tự for-each.
3. Phân biệt số phần tử đang chứa với tổng số hằng của kiểu enum khi chọn biểu diễn.
4. Vì sao enum có hơn 64 hằng vẫn sử dụng được `EnumSet`?
5. Giải thích khác biệt giữa `noneOf(MyEnum.class)`, `copyOf` một `EnumSet` rỗng và `copyOf` một danh sách rỗng.
6. Vì sao một trường bit `long` không có nghĩa toàn bộ tập chỉ chiếm 8 byte?
7. Nếu thêm một hằng enum mới, các thao tác `allOf` và phần bù có thể thay đổi thành viên như thế nào?
8. Cho một yêu cầu cần số lần xuất hiện của từng hằng. Vì sao một `EnumSet` đơn lẻ không đủ biểu diễn yêu cầu đó?

## Tài liệu đối chiếu

- [Java API — EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html): tập enum chuyên dụng, vector bit, thứ tự duyệt và hợp đồng phần tử.
- [OpenJDK 21 — RegularEnumSet](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/RegularEnumSet.java): triển khai nội bộ cho miền enum tối đa 64 hằng.
- [OpenJDK 21 — JumboEnumSet](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/JumboEnumSet.java): biểu diễn nhiều từ bit cho miền enum lớn hơn.
- [Java API — Enum.ordinal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#ordinal()): vị trí hằng trong khai báo enum.
