# Kiểm tra cùng tham chiếu trước khi so sánh trường trong `equals(Object)`

## 1. Vị trí của bước kiểm tra trong quá trình cài đặt `equals`

Khi tự cài đặt `equals(Object obj)` cho một lớp Java, bước đầu tiên thường là kiểm tra xem tham chiếu đang gọi phương thức (`this`) và tham số (`obj`) có trỏ đến **cùng một đối tượng** hay không:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }

    // Sau đó mới xác minh kiểu và so sánh các trường tham gia định nghĩa giá trị.
}
```

Đây là **mẫu phương thức minh họa, chưa phải cài đặt hoàn chỉnh**. Nếu hai tham chiếu cùng trỏ đến một đối tượng thì chắc chắn đối tượng đó bằng chính nó: kết luận ngay `true`, không cần kiểm tra thêm các trường. Nếu hai tham chiếu khác nhau, phép kiểm tra này chỉ cho biết chúng không cùng danh tính; chúng **vẫn có thể bằng nhau theo giá trị** và cần tiếp tục xử lý.

Mục tiêu của bài học là hiểu chính xác bước `this == obj`, nơi đặt nó, lợi ích và giới hạn của nó trong quy trình cài đặt `equals`. Đây là bước đầu của một phương thức `equals` đầy đủ, không thay thế bước so sánh trường.

## 2. `this == obj` thực sự kiểm tra điều gì?

Trong phương thức thể hiện (*instance method*) của Java, `this` tham chiếu đối tượng đang nhận lời gọi. Với tham số có kiểu `Object`, biểu thức `this == obj` dùng toán tử `==` trên hai **tham chiếu**:

- **`true`**: hai tham chiếu đang chỉ tới đúng một đối tượng; có thể trả về ngay `true`.
- **`false`**: chúng không phải cùng đối tượng, hoặc `obj` là `null`. Chưa thể quyết định có bằng nhau theo giá trị hay không.

Ví dụ:

```java
String first = new String("java");
String alias = first;
String second = new String("java");

System.out.println(first == alias);       // true
System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
```

`first` và `alias` là cùng một đối tượng; `first` và `second` là hai đối tượng khác nhau nhưng nội dung chuỗi bằng nhau. Vì vậy, câu `if (this == obj) return true;` **không tương đương** câu `return this == obj;` đối với lớp cần so sánh theo giá trị.

Đừng nhầm `this == obj` với việc sử dụng `==` để so sánh các trường như `String`, `List` hay đối tượng nghiệp vụ. Với trường tham chiếu, phép so sánh theo giá trị thường cần `equals` hoặc `Objects.equals`; với trường nguyên thủy thích hợp như `int` hay `long`, dùng `==` là tự nhiên.

## 3. Vì sao kiểm tra sớm? Tính phản xạ và đường đi ngắn

Hợp đồng của `Object.equals` yêu cầu **tính phản xạ** (*reflexive*): với mọi đối tượng không phải `null` là `x`, `x.equals(x)` phải là `true`. Biểu thức `this == obj` phản ánh trực tiếp quy tắc này.

Đặt kiểm tra ở đầu giúp:

1. **Đảm bảo đường đi nhanh cho trường hợp cùng tham chiếu.** Không cần đối chiếu kiểu, mở từng trường hay gọi phương thức so sánh ở đối tượng con.
2. **Thể hiện rõ ý định của người viết.** Người đọc lập tức thấy cài đặt tôn trọng tính phản xạ.
3. **Giảm thao tác không cần thiết.** Khi một đối tượng thường được so sánh với chính nó, có thể tránh các phép so sánh trường tốn công.

Về mặt hợp đồng, Java **không bắt buộc** mọi cài đặt `equals` phải có dòng `if (this == obj)`. Một cài đặt khác vẫn có thể đúng nếu luôn bảo đảm `x.equals(x)` và toàn bộ quy tắc còn lại. Tuy nhiên, kiểm tra sớm là cách đơn giản, dễ kiểm chứng và được dùng rất phổ biến.

Không nên coi đây là bảo đảm tăng hiệu năng đáng kể trong mọi ứng dụng. Lợi ích thực tế phụ thuộc dữ liệu và tần suất so sánh cùng tham chiếu. Khi phương thức chỉ so sánh hai số nguyên, chi phí bản thân việc so sánh trường đã rất thấp; tính dễ đọc và rõ hợp đồng vẫn là lý do tốt để giữ nhánh này.

**Lưu ý:** Nhánh nhanh làm cho `x.equals(x)` trả về `true`, nhưng không tự sửa một phép `equals` sai ở những nhánh khác. Tính đối xứng, bắc cầu, nhất quán và hợp đồng `hashCode` vẫn phải được kiểm tra riêng.

## 4. Thứ tự cài đặt khuyến nghị

Đối với **lớp giá trị `final`**, quy trình quen thuộc là:

1. **Kiểm tra cùng tham chiếu:** `if (this == obj) return true;`.
2. **Kiểm tra kiểu hợp lệ:** `if (!(obj instanceof MyType other)) return false;`. Mẫu `instanceof` cũng loại `null` an toàn.
3. **So sánh từng trường tham gia định nghĩa bằng nhau:** dùng toán tử hoặc phương thức tương ứng với kiểu và đặc điểm trường.
4. **Override `hashCode()` tương ứng:** các đối tượng được `equals` coi là bằng nhau phải có cùng mã băm.

Dòng kiểm tra cùng tham chiếu nên xuất hiện **trước** việc ép kiểu và so sánh trường vì ở thời điểm đó ta đã có thể kết luận. Đặt nó trước kiểm tra `null` cũng hoàn toàn an toàn: `this` không thể là `null` bên trong phương thức thể hiện đang được gọi; nếu `obj == null` thì `this == obj` đơn giản là `false`.

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof MyType other)) return false;
    return number == other.number
            && java.util.Objects.equals(label, other.label);
}
```

Đoạn trên chỉ là **khung cú pháp** cho một lớp giả định `MyType` có trường `number` và `label`; không thể biên dịch độc lập nếu chưa khai báo lớp và các trường đó.

Nếu lớp cho phép kế thừa, chọn `instanceof` hay `getClass()` phải dựa vào mô hình bằng nhau trong phân cấp: chấp nhận lớp con có thể tạo vấn đề đối xứng hoặc bắc cầu khi lớp con thêm trường; kiểm tra lớp chính xác lại loại các đối tượng khác lớp. Bài này sử dụng lớp `final` để tránh tranh chấp đó và tập trung vào bước kiểm tra cùng tham chiếu.

## 5. Ví dụ hoàn chỉnh Java 17+: hai đối tượng có thể cùng giá trị nhưng khác tham chiếu

Tạo tệp `IdentityFirstEqualsDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class IdentityFirstEqualsDemo {
    static final class AccountKey {
        private final String tenant;
        private final long id;

        AccountKey(String tenant, long id) {
            this.tenant = Objects.requireNonNull(tenant, "tenant");
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            // Bước 1: cùng tham chiếu thì chắc chắn bằng nhau.
            if (this == obj) {
                return true;
            }

            // Bước 2: sai kiểu hoặc null thì không bằng nhau.
            if (!(obj instanceof AccountKey other)) {
                return false;
            }

            // Bước 3: khác đối tượng nhưng vẫn có thể cùng giá trị.
            return id == other.id && tenant.equals(other.tenant);
        }

        @Override
        public int hashCode() {
            return 31 * tenant.hashCode() + Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("acme", 42L);
        AccountKey alias = a;
        AccountKey sameValue = new AccountKey(new String("acme"), 42L);
        AccountKey different = new AccountKey("acme", 43L);

        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(alias): " + a.equals(alias));
        System.out.println("a == sameValue: " + (a == sameValue));
        System.out.println("a.equals(sameValue): " + a.equals(sameValue));
        System.out.println("a.equals(different): " + a.equals(different));
        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("a.equals(\"acme\"): " + a.equals("acme"));
        System.out.println("same hash: " + (a.hashCode() == sameValue.hashCode()));

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(sameValue);
        System.out.println("set size: " + keys.size());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac IdentityFirstEqualsDemo.java
java IdentityFirstEqualsDemo
```

Kết quả chuẩn:

```text
a == alias: true
a.equals(alias): true
a == sameValue: false
a.equals(sameValue): true
a.equals(different): false
a.equals(null): false
a.equals("acme"): false
same hash: true
set size: 1
```

Đọc từng tình huống:

- **`a.equals(alias)`:** `alias` trỏ đúng đối tượng `a`. Nhánh `this == obj` trả ngay `true`; không thực hiện `instanceof` và không đọc trường nào.
- **`a.equals(sameValue)`:** hai lệnh `new AccountKey(...)` tạo hai đối tượng, nên nhánh đầu là `false`. Sau khi kiểm tra kiểu, giá trị `id` và `tenant` đều bằng nhau nên `equals` trả `true`. Đây là lý do không thể dừng ở `this == obj`.
- **`a.equals(different)`:** cùng kiểu nhưng `id` khác, trả `false`.
- **`a.equals(null)` và `a.equals("acme")`:** nhánh cùng tham chiếu đều `false`; `instanceof AccountKey` loại `null` hoặc kiểu khác mà không có ép kiểu nguy hiểm.
- **`HashSet`:** hai khóa bằng nhau có mã băm bằng nhau nên tập chỉ giữ một khóa tương đương.

Trong ví dụ, constructor không cho phép `tenant` là `null`, vì thế `tenant.equals(other.tenant)` an toàn. Nếu một trường tham chiếu **có thể null**, nên dùng `Objects.equals(field, other.field)` khi so sánh trường đó. Sử dụng `this == obj` không bảo vệ khỏi `NullPointerException` trong phần so sánh trường nếu mã ở phần sau viết sai.

## 6. Các lỗi dễ mắc khi viết nhánh đầu

### Lỗi 1: trả về kết quả kiểm tra tham chiếu cho toàn bộ phương thức

```java
@Override
public boolean equals(Object obj) {
    return this == obj;
}
```

Đoạn này có cùng tiêu chí định danh với `Object.equals` mặc định. Nó **không phù hợp** cho `AccountKey` trong ví dụ khi hai đối tượng khác nhau cần được xem là bằng nhau nếu cùng `tenant` và `id`. Nó chỉ phù hợp nếu lớp cố ý định nghĩa bình đẳng bằng danh tính.

### Lỗi 2: đảo điều kiện hoặc kết quả

```java
if (this == obj) {
    return false; // SAI: một đối tượng không bằng chính nó
}
```

Điều này vi phạm tính phản xạ. Ngược lại, viết `if (this != obj) return false;` cũng loại bỏ mọi trường hợp khác tham chiếu nhưng cùng giá trị. Kiểm tra đúng là **nếu cùng tham chiếu, trả `true`; nếu khác thì tiếp tục**.

### Lỗi 3: gọi `equals` của chính mình để kiểm tra cùng tham chiếu

```java
if (this.equals(obj)) {
    return true; // SAI: gọi lại cùng phương thức, dẫn đến đệ quy
}
```

Trong chính `equals(Object)`, việc gọi `this.equals(obj)` sẽ tiếp tục chạy lại `equals(Object)` với cùng đối số, có thể lặp đến `StackOverflowError`.

Không được thay bằng `Objects.equals(this, obj)` trong thân `equals` để làm phép kiểm tra tổng quát: `Objects.equals(a, b)` sẽ gọi `a.equals(b)` khi `a` và `b` là hai tham chiếu khác nhau, nên ở đây vẫn có nguy cơ đệ quy. Phép kiểm tra cần dùng là **`this == obj`**.

### Lỗi 4: ép kiểu hoặc đọc trường trước khi xác minh kiểu

```java
MyType other = (MyType) obj; // Có thể ném ClassCastException
if (this == obj) return true;
```

Với đối tượng sai kiểu, phép ép kiểu thất bại thay vì để `equals` trả `false`. Nên kiểm tra cùng tham chiếu trước, tiếp đó dùng `instanceof` hoặc chính sách kiểm tra kiểu phù hợp, rồi mới truy cập trường. Khung mã này là minh họa trong lớp `MyType`, không phải chương trình độc lập.

### Lỗi 5: dùng `==` để so sánh hai trường `String`

```java
return id == other.id && tenant == other.tenant; // SAI nếu tenant so sánh theo nội dung
```

Điều kiện trên có thể trả `false` cho hai chuỗi cùng chữ nhưng là hai đối tượng khác nhau. Kiểm tra `this == obj` đúng ở **mức đối tượng đang so sánh**; điều đó không có nghĩa mọi trường tham chiếu bên trong cũng phải dùng `==`.

## 7. Một vài giới hạn cần nắm

**Tối ưu hóa không sửa được quy tắc so sánh sai.** Ví dụ, nếu `equals` trả `true` cho hai đối tượng khác nhau do bỏ quên một trường quan trọng, nhánh `this == obj` không giúp phát hiện lỗi. Ngược lại, nếu trường mutable bị sửa sau khi dùng làm khóa `HashMap`, nhánh đầu không làm cho các cấu trúc băm tự cập nhật vị trí khóa.

**Sự khác nhau giữa `==` và `equals` phụ thuộc kiểu.** Toán tử `==` so sánh giá trị đối với kiểu nguyên thủy, nhưng ở đây cả `this` và `obj` là tham chiếu, nên `==` so sánh danh tính. Java không overload toán tử `==` cho các class tùy ý.

**Kiểm tra đầu không miễn trừ hợp đồng `hashCode`.** Nếu một lớp override `equals` theo giá trị thì phải override `hashCode` phù hợp: `a.equals(b) == true` kéo theo `a.hashCode() == b.hashCode()`. Hai đối tượng cùng hash chưa chắc bằng nhau.

**Không nhầm với `super.equals(obj)`.** Với lớp trực tiếp kế thừa `Object`, `super.equals(obj)` chỉ thực hiện so sánh tham chiếu mặc định. Nếu gọi nó như điều kiện bắt buộc rồi mới so sánh trường, hai đối tượng khác tham chiếu sẽ luôn bị loại. Việc có dùng `super.equals` hay không ở một hệ phân cấp lớp phức tạp phải căn cứ vào hợp đồng so sánh của lớp cha.

## 8. Tự kiểm tra

1. Với `Person a = new Person(...);` và `Person b = a;`, nhánh `if (this == obj)` xử lý thế nào khi gọi `a.equals(b)`?
2. Hai đối tượng mới tạo có các trường giống hệt nhau có được kết luận là khác nhau chỉ từ `this != obj` không? Vì sao?
3. Tại sao `this == obj` luôn an toàn khi `obj` là `null`, còn ép kiểu và truy cập trường cần kiểm tra tiếp?
4. Lỗi nào xảy ra nếu thay `this == obj` bằng `this.equals(obj)` ngay trong phần thân `equals`?
5. Nếu `tenant` có thể `null`, phải sửa cách so sánh trường như thế nào?
6. Vì sao `HashSet` cần cài đặt `hashCode` phù hợp, dù `equals` đã kiểm tra cùng tham chiếu?

**Ghi nhớ:** Trong `equals(Object obj)`, bắt đầu bằng `if (this == obj) return true;` để xử lý ngay trường hợp **cùng một đối tượng** và tôn trọng tính phản xạ. Khi kết quả là `false`, tiếp tục kiểm tra kiểu rồi so sánh trường để xác định **bằng nhau theo giá trị**.