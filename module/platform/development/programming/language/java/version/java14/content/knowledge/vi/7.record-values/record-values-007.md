# Tùy biến `equals`, `hashCode` và `toString` theo cùng một hợp đồng trong Java record

> **Chủ đề:** Giá trị record – Java 14. `record` từng là tính năng preview trong Java 14–15 và **đã chính thức, ổn định từ Java 16**. Bài học dùng quy tắc và API vẫn được áp dụng trong Java hiện đại, với ví dụ chạy bằng JDK 17+; không dựa vào cú pháp preview. Trọng tâm là **tính nhất quán của giá trị record**, không chỉ là cách viết ba phương thức.

## 1. Vì sao ba phương thức này cần thống nhất?

Với record đơn giản:

~~~java
record OrderLine(String sku, int quantity) {}
~~~

Java tự cung cấp constructor chuẩn, accessor `sku()`/`quantity()`, cùng ba phương thức:

- `equals(Object)` xác định **hai record có cùng giá trị** hay không.
- `hashCode()` tạo mã băm **phù hợp với cách định nghĩa bằng nhau**, để `HashSet`, `HashMap` và các cấu trúc dựa trên hash vận hành đúng.
- `toString()` cung cấp **biểu diễn văn bản dễ đọc**, thường hữu ích khi xem log hoặc debug.

Trong record mặc định, giá trị được xét dựa trên **tất cả record components**. Với component tham chiếu, Java đánh giá tương đương ngữ nghĩa `Objects.equals`; với primitive, cách so sánh phù hợp với `compare` của wrapper tương ứng. Vì vậy, `double`/`float` có một số khác biệt so với phép `==` thông thường, chẳng hạn các giá trị NaN có thể được coi là bằng nhau theo so sánh của wrapper, còn `0.0` và `-0.0` là hai kết quả so sánh khác nhau theo `Double.compare`.

Điểm quan trọng: record diễn tả một **giá trị có cấu trúc** (*shallowly immutable data carrier*). Các trường component là `private final` nhưng một đối tượng mutable được component tham chiếu vẫn có thể thay đổi nội dung. Khi tự định nghĩa `equals`, `hashCode` hoặc `toString`, bạn đang xác lập ý nghĩa của giá trị ấy và phải duy trì tính nhất quán.

### Hợp đồng chung, ba mục đích khác nhau

| Phương thức | Câu hỏi trả lời | Yêu cầu quan trọng |
| --- | --- | --- |
| `equals` | Hai instance có được xem là cùng một giá trị? | Quan hệ tương đương ổn định, phản xạ, đối xứng, bắc cầu; so với `null` là `false` |
| `hashCode` | Giá trị này đi vào “nhóm băm” nào? | **Bằng nhau thì mã băm phải giống nhau**; không yêu cầu chiều ngược lại |
| `toString` | Diễn tả giá trị này thế nào cho người đọc? | Ngắn, rõ, không lộ thông tin nhạy cảm; đối với `record`, **hai record bằng nhau phải có cùng biểu diễn chuỗi** trong trường hợp thông thường |

`toString` **không phải hàm băm** và không cần biểu diễn duy nhất: hai record khác nhau vẫn có thể hiển thị cùng chuỗi nếu bạn chủ động rút gọn, ẩn dữ liệu. Ngược lại, nếu `a.equals(b) == true` mà `a.toString()` và `b.toString()` khác nhau do in những trường bị bỏ qua trong định nghĩa bằng nhau, cách tùy biến đó không phù hợp với invariant của `java.lang.Record`.

## 2. Nắm chính xác hợp đồng của `equals` và `hashCode`

### 2.1. `equals(Object)` là quan hệ tương đương

Khi `x`, `y`, `z` là các instance hợp lệ, cần duy trì:

1. **Phản xạ (reflexive):** `x.equals(x)` là `true`.
2. **Đối xứng (symmetric):** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu (transitive):** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Nhất quán:** nếu dữ liệu dùng để so sánh không thay đổi, kết quả của những lần gọi liên tiếp không đổi.
5. **Không bằng null:** `x.equals(null)` luôn là `false`.

Record ngầm định là `final`; dùng kiểm tra `obj instanceof TenRecord other` là cách gọn để xác nhận cùng record class trong một phương thức override. Không thể có lớp con tùy ý làm mờ quan hệ bằng nhau như với nhiều class có kế thừa.

**Chữ ký override đúng:**

~~~java
@Override
public boolean equals(Object obj) {
    // Trả true khi obj mang giá trị được xem là bằng record này.
}
~~~

Phải là `public boolean equals(Object)`. Phương thức `equals(TenRecord other)` chỉ là **overload**, không thay thế `equals(Object)`; đặt `@Override` sẽ giúp compiler phát hiện chữ ký viết sai.

### 2.2. `hashCode()` theo chính quy tắc bằng nhau

Nếu `x.equals(y)` thì **bắt buộc** `x.hashCode() == y.hashCode()`. Nếu hai hash code bằng nhau, **không được** kết luận hai đối tượng bằng nhau: va chạm hash là chuyện bình thường. Kết quả băm cần ổn định khi dữ liệu tham gia so sánh không thay đổi.

~~~java
@Override
public int hashCode() {
    // Phải dùng đúng thông tin chi phối equals().
}
~~~

Không sử dụng `System.identityHashCode(this)`, mã ngẫu nhiên, thời gian hiện tại, hoặc các trường biến đổi tự do nếu `equals` so sánh theo giá trị. Với key trong `HashSet`/`HashMap`, thay đổi nội dung tham gia `hashCode` **sau khi thêm key** khiến tra cứu trở nên không đáng tin cậy.

Java **không cam kết** thuật toán hash do compiler tạo cho record sẽ giữ nguyên qua mọi phiên bản JVM hoặc mọi lần chạy; đừng lưu `hashCode()` làm ID, chữ ký số, khóa database hay checksum ổn định.

### 2.3. Ràng buộc bổ sung của `java.lang.Record`

API `java.lang.Record` nêu hai invariant đáng nhớ:

- **Copy invariant:** với record `R` có components `c1, c2, ...`, bản sao `new R(r.c1(), r.c2(), ...)` phải `equals(r)`. Nếu accessor hoặc canonical constructor chuẩn hóa/sao chép, kết quả vẫn phải bảo toàn ý nghĩa giá trị.
- **String invariant:** thông thường, hai record bằng nhau phải trả về **chuỗi `toString()` giống nhau**; ngoại lệ rất hiếm liên quan đến các component bằng nhau nhưng tự có biểu diễn chuỗi khác nhau. Khi bạn tự viết `toString` thì nên giữ invariant này một cách chủ động.

Điều này **không** có nghĩa `equals`, `hashCode` và `toString` phải có thuật toán giống nhau. Chúng phải **mô tả cùng một giá trị với các ràng buộc tương thích**, không phát sinh mâu thuẫn.

## 3. Khi nào nên giữ ba phương thức compiler sinh?

Nếu components là các kiểu đã có ngữ nghĩa bằng nhau đúng với nghiệp vụ (ví dụ `String`, số nguyên, enum, một `List` không đổi) và không cần quy tắc đặc biệt, **giữ mặc định** thường dễ hiểu và an toàn hơn tự viết.

~~~java
record OrderLine(String sku, int quantity) {}
~~~

Với hai instance `new OrderLine("A-01", 3)`, `equals` là `true`, `hashCode` bằng nhau và `toString` mặc định thể hiện tên record cùng các component. Không nên **phụ thuộc vào chuỗi ký tự chính xác** của `toString` mặc định để parse hoặc làm định dạng trao đổi dữ liệu; cách hiển thị không được cam kết là schema ổn định.

Có hai tình huống khiến bạn nên xem xét kỹ hơn:

**Trường hợp 1 – Component là mảng.**

~~~java
record RawBytes(byte[] content) {}
~~~

Hai mảng khác instance nhưng chứa `{1, 2, 3}` như nhau vẫn **không bằng nhau qua `Objects.equals`**; mảng Java kế thừa `equals` theo **identity**. Vì vậy:

~~~java
var left = new RawBytes(new byte[] {1, 2, 3});
var right = new RawBytes(new byte[] {1, 2, 3});
System.out.println(left.equals(right)); // false
~~~

Đây là **đoạn minh họa**, đặt trong phương thức. Nếu bạn muốn “giá trị của byte[]” là **nội dung các byte**, cần tự xác định cách so sánh và hash phù hợp, rồi bảo vệ mảng khỏi bị sửa sau khi tạo.

**Trường hợp 2 – Component có thể bị thay đổi.** Ví dụ `record Group(List<String> members) {}` nhận vào `ArrayList` có thể thay đổi. Dù trường tham chiếu `members` là `final`, danh sách gốc vẫn mutable; `equals`/`hashCode` của record có thể thay đổi theo thời gian. Cân nhắc `List.copyOf` trong canonical constructor để có snapshot không sửa được; nếu phần tử danh sách mutable, đó mới là **bản sao nông**, chưa phải immutable sâu.

## 4. Ví dụ hoàn chỉnh: tùy biến cả ba phương thức cho giá trị nhị phân

Yêu cầu nghiệp vụ: record `BinaryKey` được xem là bằng nhau nếu **các byte tương ứng bằng nhau**, không phụ thuộc việc hai mảng có cùng tham chiếu hay không. Hai instance bằng nhau phải có hash bằng nhau và `toString` thống nhất. Không để bên ngoài sửa nội dung giá trị sau khi khởi tạo.

Lưu chương trình dưới tên **`RecordValueDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class RecordValueDemo {

    public record BinaryKey(byte[] data) {

        // Compact canonical constructor: phòng vệ lúc nhận dữ liệu.
        public BinaryKey {
            Objects.requireNonNull(data, "data");
            data = data.clone();
        }

        // Accessor tường minh: không để caller sửa mảng bên trong.
        @Override
        public byte[] data() {
            return data.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return this == obj
                    || (obj instanceof BinaryKey other
                        && Arrays.equals(data, other.data));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(data);
        }

        @Override
        public String toString() {
            return "BinaryKey[data=" + Arrays.toString(data) + "]";
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        BinaryKey first = new BinaryKey(source);
        BinaryKey second = new BinaryKey(new byte[] {1, 2, 3});

        source[0] = 99;          // thay đổi mảng nguồn
        byte[] exposed = first.data();
        exposed[1] = 88;        // thay đổi mảng do accessor trả về

        BinaryKey copy = new BinaryKey(first.data());

        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first.toString().equals(second.toString()));
        System.out.println(first.equals(copy));
        System.out.println(first);

        Set<BinaryKey> set = new HashSet<>();
        set.add(first);
        set.add(second);
        System.out.println(set.size());

        System.out.println(Arrays.toString(first.data()));
        System.out.println(first.equals(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+; `--release 17` xác nhận mã không cần tính năng ngôn ngữ mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 RecordValueDemo.java
java RecordValueDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
true
BinaryKey[data=[1, 2, 3]]
1
[1, 2, 3]
false
~~~

### Vì sao ví dụ này đáp ứng cùng một hợp đồng?

**1. Constructor và accessor bảo toàn dữ liệu.** `data = data.clone()` trong compact constructor tạo bản sao đầu vào; compiler gán trường `this.data` khi thân constructor kết thúc. Accessor `data()` cũng trả một bản sao. Do đó, sửa `source` hoặc `exposed` không làm thay đổi dữ liệu nội bộ và không làm `hashCode` đang dùng làm khóa bị đổi.

**2. `equals` đúng theo nội dung.** `this == obj` là tối ưu hóa cho cùng instance; `instanceof BinaryKey other` bảo đảm đúng kiểu; `Arrays.equals(data, other.data)` so sánh từng byte theo thứ tự. Hai mảng có nội dung bằng nhau dù khác tham chiếu sẽ được xem là bằng nhau.

**3. `hashCode` dùng cùng một quy tắc.** `Arrays.hashCode(data)` tạo hash dựa trên **các byte** trong mảng, tương thích với `Arrays.equals`. Không dùng `data.hashCode()` vì đó là hash theo identity của mảng.

**4. `toString` thể hiện cùng nội dung giá trị.** `Arrays.toString(data)` hiển thị các byte theo thứ tự, nên hai `BinaryKey` có nội dung bằng nhau sẽ có chuỗi giống nhau. Trong ví dụ dữ liệu không nhạy cảm; **không in thẳng token, khóa mật mã, mật khẩu hay dữ liệu cá nhân** vào `toString` trong ứng dụng thật. Một biểu diễn rút gọn hoặc được che thông tin vẫn có thể hợp lệ, miễn không làm hai giá trị bằng nhau hiển thị khác nhau.

**5. Copy invariant giữ nguyên.** `new BinaryKey(first.data())` vẫn bằng `first` dù accessor trả bản sao mảng. `HashSet` chỉ có một phần tử sau khi thêm `first` và `second` vì chúng bằng nhau và hash nhất quán.

Các chương trình thực tế có thể tránh dùng mảng mutable như component nếu kiểu bất biến khác biểu diễn dữ liệu tốt hơn. Khi thật sự cần `byte[]`, thiết kế trên giúp record mang đúng ngữ nghĩa giá trị.

## 5. Một cách tốt hơn khi chỉ khác nhau về định dạng: chuẩn hóa trước khi lưu

Không phải mọi yêu cầu bình đẳng “đặc biệt” đều bắt buộc override ba phương thức. Với mã định danh **được miền nghiệp vụ quy định không phân biệt chữ hoa/thường**, có thể chuẩn hóa trong canonical constructor, rồi **giữ `equals`/`hashCode`/`toString` mặc định** của record.

Ví dụ độc lập, lưu thành **`NormalizeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class NormalizeDemo {

    public record Code(String value) {

        public Code {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (value.isBlank()) {
                throw new IllegalArgumentException("empty code");
            }
        }
    }

    public static void main(String[] args) {
        Code left = new Code(" ab-7 ");
        Code right = new Code("AB-7");

        System.out.println(left.equals(right));
        System.out.println(left.hashCode() == right.hashCode());
        System.out.println(left.value());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NormalizeDemo.java
java NormalizeDemo
~~~

~~~text
true
true
AB-7
~~~

**Vì sao đúng?** Hai giá trị đầu vào khác cách viết nhưng cùng được chuẩn hóa thành `"AB-7"` **trước khi lưu**, nên ba phương thức mặc định đã mô tả một giá trị thống nhất. `Locale.ROOT` tránh để quy tắc chữ hoa/thường phụ thuộc locale của máy chạy; tuy nhiên, **chỉ áp dụng chuẩn hóa này khi quy tắc của mã định danh cho phép**. Tên người, nội dung văn bản và định danh có phân biệt hoa/thường không nên tự tiện chuẩn hóa theo cách này. Nếu quy tắc chuẩn hóa thay đổi, cân nhắc tác động đến key và dữ liệu đã lưu.

Nguyên tắc thực hành: **thiết kế dữ liệu canonical trước**; chỉ override khi phép so sánh/hash mặc định **thật sự không thể** biểu diễn ý nghĩa giá trị cần thiết.

## 6. Những quy tắc tùy biến cần nhớ

### 6.1. Override đúng chữ ký và đúng mức truy cập

~~~java
record Token(String value) {

    @Override
    public boolean equals(Object other) {
        return other instanceof Token token
                && java.util.Objects.equals(value, token.value);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(value);
    }

    @Override
    public String toString() {
        return "Token[value=" + value + "]";
    }
}
~~~

Đây là **một khai báo record độc lập** minh họa bộ override hợp lệ. Với `String`, phép override này không cải thiện đáng kể so với ba phương thức mặc định; nó nhắc lại chính xác kiểu trả về, access modifier và cách các phương thức phải dùng cùng giá trị.

Nhầm lẫn phổ biến:

~~~java
// Chỉ là overload, KHÔNG thay thế equals(Object):
public boolean equals(Token other) {
    return other != null && value.equals(other.value);
}
~~~

Nếu khai báo trong `Token`, phương thức trên không làm thay đổi `equals(Object)` được compiler sinh. Đặt `@Override` vào một overload sai sẽ được compiler báo lỗi, vì vậy nên dùng annotation đó khi có chủ đích override.

### 6.2. Không dùng khác kiểu so sánh ở hai phía

Ví dụ lỗi logic: `equals` dùng `equalsIgnoreCase` cho một `String`, nhưng `hashCode` lại gọi `String.hashCode` trên chuỗi gốc. Hai chuỗi `"ABC"` và `"abc"` có thể được xem là bằng nhau nhưng hash khác nhau ⇒ **vi phạm hợp đồng** và làm hỏng hành vi khi dùng trong `HashSet`/`HashMap`. Cách đơn giản và nhất quán hơn là chuẩn hóa theo quy tắc miền dữ liệu trước khi lưu (mục 5); nếu thực sự phải override, cả equality và hashing phải dùng **cùng quy tắc chuẩn hóa**.

Với số thập phân `BigDecimal`, `equals` **có xét scale** (`1.0` khác `1.00`), còn `compareTo` chỉ so sánh giá trị số. Nếu muốn coi hai giá trị đó tương đương, phải thiết kế rõ cách chuẩn hóa/so sánh và hash tương ứng. Đừng chuyển một phía sang `compareTo(...) == 0` nhưng vẫn dùng hash mặc định nếu giá trị scale khác nhau có thể bị coi là bằng nhau.

Với component số thực nguyên thủy `double` hoặc `float`, tránh tùy tiện đổi equality mặc định của record thành `==`; `Double.compare`/`Float.compare` có cách xử lý NaN và signed zero cần được cân nhắc cùng với hash.

### 6.3. Mảng một chiều và mảng lồng nhau

- `byte[]`, `int[]` hoặc `String[]` **một chiều**: thường dùng bộ ba tương ứng `Arrays.equals`, `Arrays.hashCode` và `Arrays.toString`.
- Mảng **lồng nhau** như `byte[][]`: nếu muốn so sánh **nội dung theo tầng**, dùng `Arrays.deepEquals`, `Arrays.deepHashCode` và `Arrays.deepToString` cho object-array phù hợp. Phải quyết định cả việc sao chép **các mảng con**, vì `outer.clone()` mới sao chép lớp ngoài.
- Đừng mặc định `Objects.equals(a, b)` so sánh nội dung hai mảng; nó chỉ gọi `equals` của mảng, tức so sánh identity.
- `Objects.hash(data)` với một array cũng dễ gây hiểu nhầm về varargs và không phải công cụ thay thế `Arrays.hashCode(data)` để bảo đảm cùng ngữ nghĩa với `Arrays.equals`.

### 6.4. Thiết kế `toString` cho người dùng, không dùng làm serialization

- Nội dung nên **ổn định theo giá trị** và dễ đọc; nếu các record được xem là bằng nhau, không in kèm timestamp, identity hash hoặc trạng thái ngoài không ổn định khiến chuỗi của chúng khác nhau.
- Có thể ẩn hoặc rút gọn dữ liệu nhạy cảm; không nhất thiết mọi record khác nhau phải có `toString` khác nhau.
- Nếu record mang dữ liệu rất lớn, tránh xây chuỗi dài làm tốn RAM/log hoặc rò rỉ thông tin.
- Không parse `toString` mặc định để khôi phục record, dùng định dạng serialization có schema thích hợp (JSON, binary format...) nếu cần trao đổi/lưu trữ.
- `hashCode` cũng không phải định dạng lưu trữ ổn định, vì thuật toán có thể thay đổi giữa môi trường chạy và có va chạm.

## 7. Những lỗi thường gặp và hậu quả thực tế

| Sai sót | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Override `equals` nhưng giữ `hashCode` theo giá trị khác | `HashSet` có thể giữ hai phần tử được coi là bằng nhau | Định nghĩa equality/hash trên cùng thông tin |
| `equals` bỏ qua component `label`, `toString` vẫn in `label` khác nhau | Hai record bằng nhau có thể cho hai chuỗi khác nhau | Thống nhất biểu diễn hoặc cân nhắc lại khái niệm value |
| So sánh mảng bằng `==`/`Objects.equals` | Hai mảng nội dung giống nhau bị coi là khác | `Arrays.equals` hoặc `deepEquals` phù hợp |
| Hash mảng bằng `data.hashCode()` nhưng equals bằng `Arrays.equals` | Equal records có thể có hash khác nhau | `Arrays.hashCode(data)` |
| Chỉ clone mảng lúc tạo, accessor trả trực tiếp trường | Bên gọi sửa mảng bên trong, hash key thay đổi | Sao chép ở cả đầu vào và đầu ra |
| Chỉ clone accessor, constructor giữ mảng đầu vào | Bên gọi sửa mảng gốc, giá trị record thay đổi | Copy trong constructor |
| `List.copyOf` nhưng phần tử là mutable object | Có thể bị thay đổi sâu qua phần tử | Chọn phần tử immutable hoặc copy phù hợp |
| Nhầm `equals(T)` với `equals(Object)` | Không override đúng phương thức | Dùng `@Override public boolean equals(Object)` |
| Định nghĩa `toString` bằng dữ liệu nhạy cảm | Rò rỉ trong log và thông báo lỗi | Chỉ in thông tin an toàn, giới hạn |
| Dùng `hashCode` làm ID hoặc checksum | Có va chạm, không ổn định giữa lần chạy | Dùng ID/checksum theo hợp đồng riêng |

### Một ví dụ vi phạm string invariant của record

Giả sử có một record với components `id` và `displayName`. Nếu `equals` chỉ so sánh `id` nhưng `toString` giữ mặc định in **cả `id` và `displayName`**, thì hai record có cùng `id` nhưng tên hiển thị khác nhau sẽ **bằng nhau** mà có thể cho **hai chuỗi khác nhau**. Đây là lý do không nên tùy tiện biến record nhiều components thành “entity so sánh theo ID” bằng một override đơn lẻ.

Nếu nghiệp vụ cần **entity identity** dựa trên ID nhưng các thuộc tính khác thay đổi trong vòng đời, một class/entity thiết kế theo identity và lifecycle có thể rõ ràng hơn record value carrier. Nếu thực sự muốn record, cần đặt hợp đồng equality, hash, string và copy rõ ràng.

## 8. Cách kiểm tra ba phương thức trong mã thật

Các kiểm tra hữu ích gồm:

1. **Reflexive:** `a.equals(a)`.
2. **Null:** `!a.equals(null)`.
3. **Symmetric:** `a.equals(b) == b.equals(a)`.
4. **Transitive:** với `a`, `b`, `c` cùng giá trị, nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)`.
5. **Equal ⇒ same hash:** `a.equals(b)` kéo theo `a.hashCode() == b.hashCode()`. Không kiểm tra chiều ngược.
6. **Equal ⇒ same string** với record khi các component có biểu diễn chuẩn: `a.equals(b)` kéo theo `a.toString().equals(b.toString())`.
7. **Copy invariant:** `a.equals(new R(a.c1(), a.c2(), ...))`.
8. **Defensive copying:** sửa dữ liệu nguồn và dữ liệu từ accessor; `equals` và `hashCode` của record gốc phải giữ nguyên khi yêu cầu giá trị immutable.
9. **Hash-based collection:** đưa các instance equal vào `HashSet`; tập chỉ có một phần tử tương đương. Sau đó tra cứu bằng một instance mới equal.
10. **Đầu vào bất thường:** kiểm tra null, mảng rỗng, giá trị lớn, đối tượng không cùng record class, mảng lồng nhau hoặc phần tử mutable nếu thuộc miền dữ liệu.

Không chỉ kiểm tra một ví dụ “đúng”: thử cả các cặp **không bằng nhau**, các bản sao được tái tạo từ accessor, và dữ liệu bị sửa ở ranh giới. Trong `RecordValueDemo`, các phép kiểm tra equality, hash, string, copy invariant và `HashSet` cho kết quả quan sát cụ thể.

## 9. Tự luyện

1. Chạy đoạn `RawBytes` ở mục 3, giải thích vì sao hai mảng khác tham chiếu nhưng cùng byte lại bị xem là khác. Thử truyền **cùng một mảng** vào hai instance để thấy sự khác biệt.
2. Xóa riêng override `equals`, `hashCode` hoặc `toString` của `BinaryKey`. Dự đoán và quan sát điều gì không còn đúng trong ba phép kiểm tra consistency.
3. Tạo `record Matrix(int[][] values)` có bản sao phòng vệ của cả outer và inner arrays, sau đó tùy biến `equals`/`hashCode`/`toString` theo nội dung. Kiểm tra bản sao từ accessor.
4. Tạo `record ProductCode(String code)` với bất biến code không null/blank và không phân biệt hoa/thường theo **quy tắc nghiệp vụ**, áp dụng normalization trong canonical constructor, giữ ba phương thức mặc định.
5. Tạo hai record bằng nhau theo `id` nhưng khác `description`, rồi chứng minh nếu `toString` in `description` thì string invariant bị vi phạm. Đề xuất lại mô hình giá trị.
6. So sánh `BigDecimal("1.0")` và `BigDecimal("1.00")`: giải thích vì sao việc dùng `compareTo` cho equality nhưng giữ hash mặc định có thể sai.
7. Tạo `HashSet<BinaryKey>`, thêm hai instance cùng nội dung, rồi kiểm tra `contains(new BinaryKey(...))`. Thử cố ý bỏ defensive copy để thấy rủi ro khi mảng bị thay đổi sau khi thêm vào tập.

## 10. Tài liệu chính thống

- [Oracle Java 25 – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): cấu trúc record, các thành viên sinh tự động và các phương thức có thể khai báo tường minh.
- [Java SE 21 API – java.lang.Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): hợp đồng `equals`, `hashCode`, `toString`, copy invariant và string invariant.
- [Java SE 21 JLS `8.10 – Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): ngữ nghĩa Record trong ngôn ngữ Java.
- [Java SE 21 API – java.util.Arrays](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): bộ phương thức `equals`, `hashCode`, `toString` và các biến thể `deep...`.

**Điều cốt lõi:** Record mặc định đã có ngữ nghĩa giá trị dựa trên components. Khi cần tùy biến, hãy quyết định chính xác **thế nào là hai giá trị bằng nhau**, tạo hash đúng theo cùng tiêu chí, giữ chuỗi mô tả nhất quán, và bảo vệ dữ liệu mutable để kết quả không thay đổi sau khi tạo record.