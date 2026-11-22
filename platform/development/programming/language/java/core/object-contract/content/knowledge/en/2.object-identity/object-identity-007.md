# Identity hash code có thể trùng và không phải địa chỉ bộ nhớ

Trong Java, một đối tượng có **danh tính** riêng, ngay cả khi dữ liệu bên trong nó giống hệt một đối tượng khác. `System.identityHashCode(Object)` cung cấp một giá trị băm gắn với danh tính đó, hữu ích khi quan sát hoặc theo dõi các instance. Tuy nhiên, **giá trị băm không phải mã định danh duy nhất và không phải địa chỉ của đối tượng trong RAM**.

## 1. Danh tính, bằng nhau và mã băm là ba khái niệm khác nhau

- **`a == b` với hai reference:** kiểm tra hai biến có tham chiếu **cùng một đối tượng** hay không; hai instance khác nhau luôn cho `false`, kể cả khi nội dung bằng nhau.
- **`a.equals(b)`:** kiểm tra bằng nhau theo quy ước của lớp. Nếu không ghi đè `Object.equals`, quy ước mặc định chính là đồng nhất tham chiếu; các lớp như `String` thường ghi đè để so sánh giá trị.
- **`a.hashCode()`:** gọi phương thức có thể đã bị lớp ghi đè. Hợp đồng `equals`/`hashCode` yêu cầu hai đối tượng bằng nhau theo `equals` phải có cùng hash code; chiều ngược lại không đúng. Hai đối tượng không bằng nhau vẫn có thể có cùng hash code.
- **`System.identityHashCode(a)`:** lấy hash code theo cách `Object.hashCode()` mặc định sẽ làm, **bất kể lớp của `a` có ghi đè `hashCode()` hay không**. Giá trị này không được suy ra từ `equals` theo giá trị do lớp tự định nghĩa.

Ví dụ, hai `new String("java")` là hai instance khác nhau nên `==` trả về `false`, nhưng `equals` trả về `true` và `String.hashCode()` của chúng bằng nhau. **Không thể từ đó suy ra** hai giá trị `System.identityHashCode` của chúng chắc chắn khác nhau hoặc chắc chắn bằng nhau.

## 2. Những gì identity hash code bảo đảm

Với một đối tượng không đổi trong cùng một lần chạy chương trình, gọi `System.identityHashCode` nhiều lần trả lại cùng một giá trị. Hai reference cùng trỏ đến một đối tượng đương nhiên nhận cùng identity hash code. `System.identityHashCode(null)` trả về `0`.

Nhưng API **không bảo đảm** hai đối tượng khác nhau có hai identity hash code khác nhau:

- Giá trị trả về có kiểu `int`, tức chỉ có tối đa `2^32` mẫu bit có thể biểu diễn, trong khi số danh tính đối tượng có thể xuất hiện không bị giới hạn bởi một tập giá trị băm duy nhất trên mọi lần chạy.
- Cơ chế sinh băm của JVM chỉ cố gắng phân biệt các đối tượng trong điều kiện thực tế; nó không cấp số thứ tự độc nhất. **Va chạm (collision)** có nghĩa `a != b` nhưng `System.identityHashCode(a) == System.identityHashCode(b)`.
- Hai đối tượng khác nhau có thể va chạm; phép so sánh hai số băm bằng nhau **không chứng minh** hai reference trỏ cùng một đối tượng. Ngược lại, nếu hai identity hash code khác nhau thì các reference đó không thể cùng trỏ một đối tượng tại thời điểm so sánh trong cùng lần chạy.
- Giá trị băm không được bảo đảm giữ nguyên giữa các lần khởi động JVM, giữa máy, phiên bản JVM hoặc cách cấu hình runtime. Đừng lưu nó như khóa danh tính bền vững.

Nguyên lý chiếc hộp (pigeonhole principle) cho thấy không thể dùng một số `int` làm mã duy nhất cho số lượng danh tính tùy ý. **Không cần tạo hàng tỷ đối tượng để chứng minh giới hạn này**, và một ví dụ nhỏ không xảy ra va chạm cũng không chứng minh rằng va chạm là bất khả thi.

## 3. Vì sao identity hash code không phải địa chỉ bộ nhớ?

Java cung cấp *reference* để truy cập đối tượng, nhưng Java API không công bố địa chỉ vật lý hoặc địa chỉ bộ nhớ máy ảo của đối tượng thông qua `System.identityHashCode`. JVM được quyền tổ chức heap và cài đặt identity hashing theo nhiều cách.

- Bộ gom rác có thể **di chuyển đối tượng** trong bộ nhớ, trong khi identity của đối tượng và identity hash code trong một lần chạy vẫn giữ được ý nghĩa. Vì vậy không thể đồng nhất giá trị hash với vị trí bộ nhớ tại một thời điểm.
- Chi tiết lưu trữ hash (chẳng hạn trong metadata của object hoặc cấu trúc bên ngoài) là chi tiết triển khai JVM, **không phải hợp đồng của Java**.
- Biểu diễn thường gặp như `java.lang.Object@4e25154f` đến từ cách `Object.toString()` mặc định ghép tên lớp với `Integer.toHexString(hashCode())`. Chuỗi hex sau `@` là **hash code ở hệ 16**, không phải con trỏ. Nếu lớp ghi đè `toString()` hoặc `hashCode()`, kết quả hiển thị còn có thể khác.
- Dù một JVM cụ thể dùng thông tin liên quan đến địa chỉ trong thuật toán hashing, từ đó vẫn **không thể suy ngược một địa chỉ chính xác hay ổn định** theo đặc tả Java.

Vì vậy, không nên đọc các số như `0x4e25154f` thành địa chỉ heap, dùng chúng để tính khoảng cách giữa các object, hoặc giả định object sẽ nằm mãi ở một vị trí.

## 4. Ví dụ Java 17+ có thể chạy trực tiếp

Lưu đoạn sau trong tệp `IdentityHashCodeDemo.java`:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashCodeDemo {
    public static void main(String[] args) {
        Object original = new Object();
        Object alias = original;
        Object another = new Object();

        System.out.println("alias == original: " + (alias == original));
        System.out.println("another == original: " + (another == original));
        System.out.println("alias identity hash matches: "
                + (System.identityHashCode(alias) == System.identityHashCode(original)));
        System.out.println("Object.hashCode matches identityHashCode: "
                + (original.hashCode() == System.identityHashCode(original)));
        System.out.println("identityHashCode(null): " + System.identityHashCode(null));

        String one = new String("java");
        String two = new String("java");
        System.out.println("one == two: " + (one == two));
        System.out.println("one.equals(two): " + one.equals(two));
        System.out.println("one.hashCode() == two.hashCode(): "
                + (one.hashCode() == two.hashCode()));

        Map<String, Integer> valueKeys = new HashMap<>();
        Map<String, Integer> identityKeys = new IdentityHashMap<>();
        valueKeys.put(one, 1);
        valueKeys.put(two, 2);
        identityKeys.put(one, 1);
        identityKeys.put(two, 2);
        System.out.println("HashMap size: " + valueKeys.size());
        System.out.println("IdentityHashMap size: " + identityKeys.size());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac IdentityHashCodeDemo.java
java IdentityHashCodeDemo
```

Kết quả chuẩn, không phụ thuộc các con số hash cụ thể:

```text
alias == original: true
another == original: false
alias identity hash matches: true
Object.hashCode matches identityHashCode: true
identityHashCode(null): 0
one == two: false
one.equals(two): true
one.hashCode() == two.hashCode(): true
HashMap size: 1
IdentityHashMap size: 2
```

**Đọc kết quả đúng cách:**

1. `original` và `alias` cùng trỏ tới một instance, nên `==` và phép đối chiếu identity hash code đều cho `true`. `another` là một instance mới nên `==` với `original` cho `false`; ví dụ **không khẳng định** identity hash code của hai instance này bắt buộc khác nhau.
2. `original` thuộc đúng lớp `Object`, không ghi đè `hashCode()`, nên `original.hashCode()` và `System.identityHashCode(original)` bằng nhau. Điều đó **không áp dụng mặc định cho mọi lớp có ghi đè `hashCode()`**.
3. `one` và `two` có nội dung giống nhau nên `String.equals` và `String.hashCode` xem chúng như các giá trị bằng nhau. `HashMap` thay thế giá trị của khóa tương đương nên còn 1 entry.
4. `IdentityHashMap` dùng **`==` cho key**, nên `one` và `two` là hai key khác nhau và map có 2 entry. Nó sử dụng identity hash code phục vụ tra cứu nhưng **vẫn đối chiếu danh tính thực tế để xử lý va chạm**; không coi số hash trùng là cùng một key.

Ví dụ chủ ý **không in một số identity hash code cố định**, vì những số đó phụ thuộc runtime. Nó cũng không dùng phép `identityHashCode(one) != identityHashCode(two)` như bằng chứng hai instance khác nhau: điều đó có thể đúng ở một lần chạy mà không phải bảo đảm của API.

## 5. Cách áp dụng và những sai lầm cần tránh

| Mục đích | Cách phù hợp | Cách dễ sai |
| --- | --- | --- |
| Kiểm tra hai reference có cùng đối tượng | `a == b` | `System.identityHashCode(a) == System.identityHashCode(b)` |
| So sánh hai giá trị logic | `equals` và `hashCode` đúng hợp đồng của lớp | Dùng identity hash code thay cho so sánh giá trị |
| Tạo map phân biệt instance, kể cả khi `equals` bằng nhau | `IdentityHashMap` trong trường hợp thật sự cần identity semantics | Lấy identity hash code làm key `Integer` và bỏ qua va chạm |
| Ghi log để liên hệ các lần xuất hiện của một instance trong một lần chạy | Có thể hiển thị tên lớp cùng identity hash code **như nhãn gợi ý**, và xác nhận bằng reference khi cần | Coi nhãn đó là ID độc nhất qua mọi object và mọi lần chạy |
| Cần ID độc nhất, lưu lâu dài hoặc trao đổi giữa tiến trình | Cấp ID riêng theo bài toán, ví dụ UUID hoặc bộ sinh ID có quản lý vòng đời | Lưu `System.identityHashCode` hoặc hậu tố `Object.toString()` |
| Cần điều tra vị trí object trong bộ nhớ | Dùng công cụ chẩn đoán JVM phù hợp và chấp nhận tính phụ thuộc môi trường | Suy ra địa chỉ từ số hash hoặc chuỗi hex sau `@` |

**Lưu ý khi debug:** hai dòng log có identity hash code giống nhau vẫn có thể đến từ hai instance khác nhau. Khi sự khác biệt danh tính có ảnh hưởng đến đúng/sai của chương trình, phải dựa trên reference hoặc một cơ chế gắn ID riêng được thiết kế để không nhập nhằng trong phạm vi yêu cầu.

## 6. Tự kiểm tra kiến thức

- Nếu `a == b` là `true`, hai lần gọi `System.identityHashCode(a)` và `System.identityHashCode(b)` trong cùng lần chạy có bằng nhau không? **Có**, vì đó là cùng một đối tượng.
- Nếu hai identity hash code bằng nhau, có kết luận `a == b` không? **Không**, vì có thể xảy ra va chạm.
- Nếu `a.equals(b)` là `true`, identity hash code có bắt buộc bằng nhau không? **Không**, bởi `equals` có thể so sánh giá trị của hai instance khác nhau; hợp đồng bắt buộc áp dụng cho `a.hashCode()` và `b.hashCode()`, không phải identity hash code.
- Có thể lấy địa chỉ bộ nhớ bằng `Integer.toHexString(System.identityHashCode(a))` không? **Không**: thao tác đó chỉ đổi cách biểu diễn cùng một số băm sang hệ 16.

**Ghi nhớ:** danh tính được quyết định bởi **cùng reference** (`==`); identity hash code là **giá trị băm hỗ trợ**, có thể va chạm và không biểu diễn địa chỉ bộ nhớ.
