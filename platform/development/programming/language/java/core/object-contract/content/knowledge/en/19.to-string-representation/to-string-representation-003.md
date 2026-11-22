# Vì sao phần sau @ không được hiểu là địa chỉ bộ nhớ

## 1. Hiện tượng thường gặp khi in một object

Khi in một đối tượng Java chưa tự định nghĩa cách biểu diễn chuỗi, ta thường thấy dạng:

```text
com.example.Person@5acf9800
```

Nhiều người nhìn phần `5acf9800` sau dấu `@` rồi gọi đó là “địa chỉ bộ nhớ” của đối tượng. Kết luận này **không được hợp đồng Java bảo đảm và vì thế không chính xác**. Ở cách biểu diễn mặc định từ `java.lang.Object.toString()`, phần sau dấu `@` là **giá trị `hashCode()` của đối tượng, được định dạng thành chuỗi thập lục phân (hex)**.

Hệ quả quan trọng:

- Không thể suy ra vị trí đối tượng trong RAM từ chuỗi `ClassName@hex`.
- Hai đối tượng **khác tham chiếu** vẫn có thể in ra **cùng** hậu tố sau `@`.
- Giá trị hash không phải ID duy nhất hoặc địa chỉ ổn định dùng để lưu lại giữa các lần chạy chương trình.
- Nếu lớp ghi đè `hashCode()`, hậu tố của `Object.toString()` có thể phản ánh quy tắc hash do lập trình viên định nghĩa, hoàn toàn không liên quan đến cơ chế cấp phát bộ nhớ.
- Nếu lớp ghi đè `toString()`, chuỗi in ra thậm chí **không cần có ký tự `@`**.

Bài này tập trung vào **cách hiểu chuỗi `toString()` mặc định**, nhất là nguồn gốc và giới hạn ý nghĩa của phần sau dấu `@`.

## 2. Công thức thực sự của Object.toString()

Theo hợp đồng của `java.lang.Object.toString()`, cách biểu diễn mặc định tương đương với:

```java
getClass().getName() + "@" + Integer.toHexString(hashCode())
```

Đây là **biểu thức minh họa cơ chế của phương thức**, không phải một chương trình Java độc lập. Mỗi thành phần có nhiệm vụ rõ ràng:

| Thành phần | Ý nghĩa |
| --- | --- |
| `getClass()` | Lấy lớp **thực tế lúc chạy** của đối tượng. |
| `getClass().getName()` | Trả tên lớp dạng nhị phân mà Java dùng cho `Class.getName()`, ví dụ `com.example.Person`. |
| `"@"` | Ký tự phân cách giữa tên lớp và hậu tố hash. |
| `hashCode()` | Lấy số nguyên `int` do phương thức `hashCode()` của đối tượng trả về. |
| `Integer.toHexString(...)` | Chuyển mẫu bit của số nguyên `int` thành biểu diễn hex không dấu, dùng các ký tự `0–9` và `a–f`. |

Giả sử `hashCode()` trả về số thập phân `42`:

```java
System.out.println(Integer.toHexString(42)); // 2a
```

Do đó, đối tượng của lớp `Person` đang dùng `Object.toString()` và có `hashCode() == 42` sẽ được hiển thị với hậu tố `@2a`. Số `2a` trong hệ 16 chỉ là một cách viết khác của `42` trong hệ 10. Nó không chứa thông tin bắt buộc về vùng nhớ.

Cần phân biệt **giá trị hash** với **kích thước/vị trí tham chiếu**. `hashCode()` trả về `int` 32 bit; địa chỉ vùng nhớ trong một tiến trình có thể có cách biểu diễn, kích thước và cơ chế quản lý hoàn toàn khác. Việc hậu tố có ký tự hex khiến nó trông giống địa chỉ chỉ là sự giống nhau về cách viết.

### Chú ý về tên lớp

Nếu đối tượng là instance của lớp lồng, `getClass().getName()` có thể chứa ký tự `$`. Nếu là một mảng nguyên thủy kiểu `int[]`, tên từ `getClass().getName()` là `[I`, nên đầu ra mặc định của đối tượng mảng có dạng `[I@...`. Các quy tắc tên lớp này cũng không nói gì về vị trí bộ nhớ.

Ví dụ:

```java
int[] values = {1, 2, 3};
System.out.println(values.getClass().getName()); // [I
System.out.println(java.util.Arrays.toString(values)); // [1, 2, 3]
```

*Đây là các lệnh minh họa trong một phương thức.* Muốn xem **nội dung** mảng, dùng `Arrays.toString` hoặc `Arrays.deepToString` khi phù hợp, thay vì cố giải mã hậu tố sau `@`.

## 3. Hash code không phải địa chỉ và cũng không phải danh tính duy nhất

`Object.hashCode()` trả về một số nguyên phục vụ hợp đồng băm của Java. Đối với `Object.hashCode()` mặc định, Java mô tả ý định tạo các mã khác nhau cho các object khác nhau “khi khả thi”, nhưng **không bảo đảm các mã luôn duy nhất**.

Một số điểm giúp tránh hiểu nhầm:

1. **Không có API địa chỉ bộ nhớ trong `hashCode()`.** Đặc tả Java không yêu cầu `Object.hashCode()` tính bằng cách lấy địa chỉ RAM.
2. **Va chạm hash là hợp lệ.** Hai object khác nhau có thể có cùng hash mà không vi phạm hợp đồng.
3. **Hash không xác định equality theo chiều ngược lại.** Nếu `a.equals(b)` là `true` thì chúng phải có hash bằng nhau; nhưng cùng hash không chứng minh `equals()` là `true`.
4. **Hậu tố không phải khóa lưu trữ.** Không dùng `@...` làm ID database, khóa phiên, định danh theo dõi liên tiến trình hoặc giá trị bí mật.
5. **Giá trị không có cam kết lặp lại qua nhiều lần chạy.** Với hash mặc định, chương trình khởi động lại không có nghĩa các object mới cùng loại sẽ có hậu tố cũ.
6. **JVM được tự do triển khai cơ chế của hash mặc định** miễn giữ hợp đồng ngôn ngữ/API. Một triển khai nào đó có thể dựa một phần vào thông tin liên quan đến đối tượng, nhưng không được suy luận từ đó rằng mọi JVM hay mọi lần chạy đều xuất địa chỉ bộ nhớ.

Đặc biệt, garbage collector có thể di chuyển đối tượng trong bộ nhớ trong một số cấu hình JVM. Java vẫn yêu cầu `hashCode()` của một object nhất quán trong cùng quá trình thực thi khi thông tin liên quan đến equality không đổi. Do đó, ngay cả trong môi trường có quản lý bộ nhớ di chuyển, chuỗi hash cũng không thể được hiểu như một bản chụp địa chỉ đang tồn tại ở mọi thời điểm.

## 4. Thí nghiệm quan trọng: hai object khác nhau cùng in @2a

Ta không cần đo đạc vùng nhớ để chứng minh phần sau `@` **không phải địa chỉ**. Chỉ cần tạo một lớp **giữ `toString()` mặc định** nhưng **ghi đè `hashCode()`** để trả một hằng số. Khi đó mọi instance của lớp sẽ có cùng hậu tố dù là các object riêng biệt.

Tạo tệp `ToStringAtDemo.java`:

```java
public class ToStringAtDemo {

    static final class FixedHash {
        private final String label;

        FixedHash(String label) {
            this.label = label;
        }

        @Override
        public int hashCode() {
            return 42;
        }
        // Không ghi đè toString() và equals().
    }

    static final class Described {
        private final String label;

        Described(String label) {
            this.label = label;
        }

        @Override
        public int hashCode() {
            return 255;
        }

        @Override
        public String toString() {
            return "Described(label=" + label + ")";
        }
    }

    public static void main(String[] args) {
        FixedHash first = new FixedHash("A");
        FixedHash second = new FixedHash("B");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.toString().equals(second.toString()));

        System.out.println(first.getClass().getName());
        System.out.println(Integer.toHexString(first.hashCode()));
        System.out.println(first.getClass().getName() + "@"
                + Integer.toHexString(first.hashCode()));

        System.out.println(new Described("third"));
        System.out.println(String.valueOf((Object) null));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn, tại thư mục chứa tệp:

```bash
javac ToStringAtDemo.java
java ToStringAtDemo
```

Đầu ra chính xác trong package mặc định như mã trên:

```text
ToStringAtDemo$FixedHash@2a
ToStringAtDemo$FixedHash@2a
false
false
true
ToStringAtDemo$FixedHash
2a
ToStringAtDemo$FixedHash@2a
Described(label=third)
null
```

Giải thích từng bước:

1. `first` và `second` đều là `FixedHash`, được tạo bằng hai lần `new` nên `first == second` là `false`.
2. `FixedHash` không ghi đè `equals()`, vì vậy phép so tham chiếu mặc định cũng cho `first.equals(second) == false`.
3. `FixedHash` ghi đè `hashCode()` để luôn trả `42`; `Integer.toHexString(42)` là `2a`.
4. `FixedHash` không ghi đè `toString()`. Lời gọi `Object.toString()` của **mỗi** instance sẽ gọi `hashCode()` đã ghi đè. Bởi vậy cả hai object in ra cùng chuỗi `ToStringAtDemo$FixedHash@2a`.
5. Chuỗi `toString()` của chúng giống nhau (`true`) trong khi **hai object không cùng tham chiếu và không bằng nhau theo `equals()`**. Vậy phần sau `@` không thể được hiểu như địa chỉ duy nhất của mỗi object.
6. `Described` có ghi đè `toString()`, nên dù `hashCode() == 255`, chuỗi hiển thị chỉ là `Described(label=third)`. Công thức `ClassName@hex` chỉ áp dụng khi đang dùng cách biểu diễn mặc định.
7. Với giá trị `null`, `String.valueOf((Object)null)` trả chuỗi `"null"`; không có object thực sự để gọi `getClass()` hay `hashCode()`.

Tên `ToStringAtDemo$FixedHash` có dấu `$` vì đây là lớp lồng `static` và `Class.getName()` trả tên nhị phân của lớp. Nếu đưa lớp vào package khác, phần tên lớp in ra sẽ thêm tiền tố package, nhưng logic về hậu tố `@2a` không thay đổi.

### Điểm tinh tế: Object.toString() vẫn gọi hashCode() theo cơ chế ghi đè

Một lớp có thể **không** định nghĩa `toString()` nhưng **có** định nghĩa `hashCode()`. Khi `Object.toString()` thực hiện lời gọi `hashCode()` trên đối tượng, Java áp dụng dynamic dispatch để chạy phiên bản phù hợp với lớp runtime. Vì vậy, không nên nói rằng hậu tố sau `@` luôn là “identity hash” ngay cả khi `toString()` còn dùng mặc định.

Trong thí nghiệm, hậu tố được sinh trực tiếp từ phương thức `FixedHash.hashCode()` do lập trình viên viết. Đó là một số do chương trình quyết định, không phải thông tin bộ nhớ mà JVM tiết lộ.

## 5. Phân biệt hashCode() với System.identityHashCode()

Java còn có:

```java
int identityHash = System.identityHashCode(object);
```

*Đây là một đoạn lệnh minh họa trong phương thức, với `object` đã được khai báo.*

`System.identityHashCode(object)` trả về mã hash giống cách tính **`Object.hashCode()` mặc định** cho đối tượng ấy, **ngay cả khi lớp đã ghi đè `hashCode()`**. Điều này hữu ích khi cần quan sát theo identity trong công cụ debug. Tuy nhiên, **identity hash cũng không phải địa chỉ bộ nhớ** và **không được cam kết duy nhất**.

| Biểu thức | Nguồn giá trị | Có chắc là địa chỉ bộ nhớ? |
| --- | --- | --- |
| `object.hashCode()` | Phương thức `hashCode()` thực tế; có thể do lớp ghi đè. | Không. |
| `System.identityHashCode(object)` | Hash theo semantics mặc định của `Object`, bỏ qua override `hashCode()`. | Không. |
| `Integer.toHexString(object.hashCode())` | Cách biểu diễn hex của hash thông thường. | Không. |
| `Object.toString()` mặc định | Tên lớp + `@` + hex của `object.hashCode()`. | Không. |
| `object.toString()` nếu lớp ghi đè | Chuỗi do lớp tự định nghĩa. | Không thể suy đoán định dạng từ Object mặc định. |

Điều gì xảy ra trong ví dụ `FixedHash`?

- `first.hashCode() == 42` là giá trị chắc chắn vì lớp đã ghi đè phương thức.
- `System.identityHashCode(first)` do JVM cấp theo quy tắc identity hash, **không** bị ép thành `42`.
- Trị số identity hash thực tế không được bảo đảm và có thể tình cờ bằng hoặc khác `42`; vì vậy bài không ghi stdout giả định cho nó.

Ngay cả `System.identityHashCode(first) == System.identityHashCode(second)` cũng không đủ chứng minh hai biến đang trỏ cùng object: hai object khác nhau có thể xảy ra hash collision. Muốn hỏi có đúng cùng instance hay không, dùng `first == second`. Muốn hỏi bình đẳng logic theo lớp, dùng `first.equals(second)`.

## 6. Liên hệ với equals() và hashCode(): ba khái niệm khác nhau

Có ba câu hỏi cần giữ tách bạch:

| Câu hỏi | Cách kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Hai biến có trỏ cùng instance không? | `a == b` | Đồng nhất tham chiếu. |
| Hai object có bằng nhau về giá trị logic không? | `a.equals(b)` | Theo hợp đồng và cách triển khai của lớp. |
| Hai object có cùng mã băm không? | `a.hashCode() == b.hashCode()` | So hai giá trị `int`, chỉ là thông tin hỗ trợ băm. |

Hợp đồng Java bắt buộc: **nếu hai object bằng nhau theo `equals()` thì hash của chúng phải bằng nhau**. Chiều ngược lại không đúng: hai object khác nhau có thể có cùng hash. Vì vậy việc các object in cùng hậu tố hex không chứng minh chúng bằng nhau.

Trong ví dụ `FixedHash`, tất cả các instance đều có hash `42` nhưng `equals()` mặc định vẫn chỉ công nhận cùng tham chiếu. Đây là lựa chọn hash chất lượng rất kém cho collection băm nếu có nhiều đối tượng, vì gây nhiều collision, nhưng **không vi phạm hợp đồng `equals()/hashCode()`**. Ta cố ý dùng nó để tách bạch hash với địa chỉ.

Một lỗi khác: lớp ghi đè `equals()` theo các trường nhưng quên ghi đè `hashCode()` phù hợp. Hai object có thể equals nhau mà hash khác nhau, vi phạm hợp đồng và khiến `HashMap`/`HashSet` xử lý tra cứu không đúng. Đừng lấy hậu tố `@...` để quyết định equality; hãy thiết kế `equals()/hashCode()` đúng vai trò.

## 7. Vì sao giá trị hậu tố không phù hợp làm mã định danh lâu dài?

Giả sử ứng dụng ghi một log:

```text
RequestContext@6d03e736 started
```

Một kỹ sư khác tìm chuỗi `6d03e736` và muốn dùng làm ID để gắn các bản ghi trong database hoặc theo dõi xuyên nhiều lần khởi động. Điều đó không an toàn vì:

- **Không đảm bảo không trùng:** một giá trị hash 32 bit có thể bị nhiều object sử dụng.
- **Không cam kết ổn định qua tiến trình hoặc lần chạy khác:** khởi động lại JVM không tạo ra phép ánh xạ định danh có hợp đồng duy trì.
- **Có thể bị ghi đè:** lớp thay đổi cách tính `hashCode()` sau khi cập nhật thư viện sẽ khiến hậu tố đổi ý nghĩa.
- **Không gắn với lifecycle:** không có lời hứa rằng hậu tố cho biết object còn sống, đã được GC thu gom hay đã bị dịch chuyển vùng nhớ.
- **Không mô tả nội dung:** người đọc không thể biết các trường quan trọng của một yêu cầu chỉ từ `@6d03e736`.

Nếu cần theo dõi yêu cầu qua log, hãy tạo request ID/correlation ID có quản lý, ví dụ một UUID theo từng request, rồi truyền nó qua các bước xử lý. Nếu cần ID nghiệp vụ lâu dài, dùng khóa nghiệp vụ hoặc định danh được hệ thống cấp. Nếu chỉ cần đọc trạng thái object để debug, ghi đè `toString()` theo những trường hữu ích và loại trừ thông tin nhạy cảm.

**Lưu ý bảo mật:** Tránh đưa mật khẩu, token, khóa truy cập hoặc dữ liệu cá nhân nhạy cảm vào `toString()`. Nhiều framework hoặc logger có thể gọi `toString()` khi trình bày đối tượng; một chuỗi dễ đọc không đáng để làm lộ dữ liệu.

## 8. Nếu lớp ghi đè toString(), còn dấu @ thì sao?

Công thức `ClassName@hex` là cách biểu diễn **mặc định của `Object.toString()`**, không phải cấu trúc bắt buộc của mọi chuỗi Java.

Một lớp có thể viết:

```java
@Override
public String toString() {
    return "User{id='" + id + "', status='" + status + "'}";
}
```

*Đây chỉ là phần thân của phương thức nằm trong một lớp có các trường `id` và `status`; không phải chương trình độc lập.*

Khi đó chuỗi in ra do phương thức ghi đè quyết định. Nó có thể không có dấu `@`, hoặc có dấu `@` như một phần giá trị bình thường, chẳng hạn địa chỉ email `a@example.com`. Vì vậy **đừng viết parser đoán địa chỉ hoặc mã băm dựa vào ký tự `@` trong mọi `toString()`**.

Ngay cả với đối tượng chưa ghi đè `toString()`, ký tự `@` chỉ phân cách tên lớp và biểu diễn hash; thông tin đó thường không giúp tái tạo object hay nội dung dữ liệu. Nếu hệ thống cần định dạng máy đọc được, dùng serializer/DTO với schema rõ ràng thay cho dựa vào chuỗi debug.

## 9. Một số hiểu nhầm và cách sửa

### Hiểu nhầm 1: “@ đi sau tên lớp nên chắc là địa chỉ”

Sự thật: `Object.toString()` kết hợp `getClass().getName()`, `@` và `Integer.toHexString(hashCode())`. Định dạng trông giống địa chỉ chỉ là cách trình bày hex.

### Hiểu nhầm 2: “Hai object khác nhau luôn có hậu tố khác nhau”

Sự thật: hash collision là hợp lệ. Ví dụ `FixedHash` đã chứng minh hai đối tượng mới khác nhau có thể cùng `@2a`.

### Hiểu nhầm 3: “Cùng hậu tố thì equals() bằng nhau”

Sự thật: cùng hash không suy ra `equals()`. Mặt khác, hai object `equals()` nhau bắt buộc có cùng `hashCode()` theo hợp đồng.

### Hiểu nhầm 4: “Nếu dùng System.identityHashCode() thì sẽ ra địa chỉ thật”

Sự thật: `identityHashCode` là mã băm theo semantics identity, nhưng API vẫn không hứa trả về địa chỉ bộ nhớ hoặc giá trị không bao giờ trùng.

### Hiểu nhầm 5: “Đổi toString() cũng thay hashCode()”

Sự thật: hai phương thức độc lập về trách nhiệm. Ghi đè `toString()` thay cách biểu diễn, không tự thay cách `equals()` hoặc `hashCode()` hoạt động. Ngược lại, ghi đè `hashCode()` có thể làm hậu tố của **Object.toString() mặc định** đổi theo.

### Hiểu nhầm 6: “Số hex cho biết thứ tự tạo object”

Sự thật: `hashCode()` không có hợp đồng tăng dần theo lần cấp phát. So sánh độ lớn của hai hậu tố không xác định object nào được tạo trước.

### Hiểu nhầm 7: “Có thể dùng chuỗi @hex làm key cho HashMap”

Về mặt cú pháp có thể đặt bất kỳ chuỗi nào làm key, nhưng dùng `toString()` mặc định làm định danh logic là thiết kế thiếu bảo đảm. Hãy chọn các trường identity/value thực sự, dùng kiểu khóa bất biến và triển khai `equals()/hashCode()` nhất quán.

### Hiểu nhầm 8: “Có thể nhìn một log @hex rồi xác định object ở địa chỉ nào”

Không. Định dạng `@hex` không cung cấp API tra cứu địa chỉ hay giải tham chiếu. Phân tích heap hoặc bộ nhớ thực tế cần công cụ chẩn đoán JVM thích hợp; ngay cả những công cụ ấy có khái niệm địa chỉ/ID phụ thuộc snapshot và runtime, không thể tự suy từ `Object.toString()`.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `Person@2a` với `Object.toString()` mặc định có nghĩa `Person` được lưu tại địa chỉ RAM `0x2a` không?  
**Đáp án:** Không. `2a` là biểu diễn hex của giá trị `hashCode()`, tức số thập phân `42`.

**Câu 2.** Hai object mới khác nhau có cùng chuỗi `SomeClass@2a` được không?  
**Đáp án:** Có. Nếu cùng tên lớp và cùng hash, `Object.toString()` mặc định tạo ra cùng chuỗi dù hai tham chiếu khác nhau.

**Câu 3.** Nếu chỉ ghi đè `hashCode()` thành `return 255;` nhưng vẫn dùng `Object.toString()`, hậu tố là gì?  
**Đáp án:** `@ff` vì `255` trong hệ 16 là `ff`.

**Câu 4.** `System.identityHashCode(obj)` có bảo đảm trả địa chỉ bộ nhớ hoặc một ID duy nhất không?  
**Đáp án:** Không. Nó bỏ qua override `hashCode()` để lấy identity hash, nhưng vẫn là hash chứ không phải API địa chỉ.

**Câu 5.** Hai object cùng hash có chắc bằng nhau theo `equals()`?  
**Đáp án:** Không. Cùng hash chỉ là điều kiện bắt buộc của các object bằng nhau; hash collision giữa các object không bằng nhau được phép.

**Câu 6.** Tại sao `Arrays.toString(array)` thích hợp hơn `array.toString()` để xem nội dung mảng một chiều?  
**Đáp án:** `array.toString()` dùng cách hiển thị mặc định kiểu `[I@...`, còn `Arrays.toString` hiển thị từng phần tử.

**Câu 7.** Một lớp tự ghi đè `toString()` thành `"User(email=a@example.com)"` thì ký tự `@` có còn mang nghĩa hash không?  
**Đáp án:** Không. Khi phương thức ghi đè tự quyết định định dạng, dấu `@` có thể chỉ là một ký tự văn bản thông thường.

**Câu 8.** Khi cần gắn ID xuyên nhiều request và nhiều lần khởi động JVM, có nên lưu phần sau `@` không?  
**Đáp án:** Không. Dùng định danh có hợp đồng rõ ràng, chẳng hạn request ID, UUID hoặc khóa nghiệp vụ phù hợp.

**Ghi nhớ:** Với `Object.toString()` mặc định, phần sau dấu `@` là **`Integer.toHexString(hashCode())`**, hoàn toàn không có cam kết đại diện cho địa chỉ RAM, thứ tự tạo object hay một định danh duy nhất. Muốn so object, dùng hợp đồng `equals()/hashCode()`; muốn kiểm tra cùng instance, dùng `==`; muốn quan sát dữ liệu, xây dựng `toString()` có ý nghĩa hoặc dùng công cụ chẩn đoán đúng mục đích.