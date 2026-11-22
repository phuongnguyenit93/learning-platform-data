# Cùng hash code không suy ra `equals()`

## Mục tiêu bài học

Trong Java, `hashCode()` và `equals(Object)` cùng tham gia xác định cách đối tượng hoạt động trong các cấu trúc dựa trên băm như `HashMap` và `HashSet`. Tuy nhiên, **hai đối tượng có cùng mã băm chưa chắc bằng nhau**. Đây là chiều suy luận rất dễ bị đảo ngược khi đọc hợp đồng `hashCode`.

Sau bài này, bạn có thể:

- Phát biểu chính xác chiều **bắt buộc** và chiều **không được suy ra** giữa `equals()` và `hashCode()`.
- Giải thích vì sao collision (đụng độ băm) là hiện tượng hợp lệ và không đồng nghĩa với lỗi.
- Dự đoán kết quả của các ví dụ `String` có cùng hash nhưng `equals() == false`.
- Hiểu vì sao `HashMap`/`HashSet` vẫn có thể chứa hai khóa hoặc phần tử khác nhau dù có cùng `hashCode()`.
- Cài đặt `equals`/`hashCode` nhất quán, nhận diện lỗi ở chiều bắt buộc và tránh các giả định sai về tính duy nhất của hash.

## 1. Hai chiều suy luận không tương đương

Hợp đồng `Object.hashCode()` quy định: **nếu hai đối tượng bằng nhau theo `equals(Object)`, chúng bắt buộc có cùng mã băm**.

Viết dưới dạng mệnh đề:

```text
a.equals(b) == true
           ↓ bắt buộc
a.hashCode() == b.hashCode()
```

Chiều ngược lại **không được bảo đảm**:

```text
a.hashCode() == b.hashCode()
           ↓ không đủ kết luận
a.equals(b) có thể true hoặc false
```

Bảng dưới đây giúp phân biệt:

| `a.equals(b)` | `a.hashCode() == b.hashCode()` | Hợp đồng |
| --- | --- | --- |
| `true` | `true` | Đúng và bắt buộc |
| `true` | `false` | **Sai:** vi phạm hợp đồng `hashCode` |
| `false` | `true` | **Hợp lệ:** hai đối tượng khác nhau nhưng trùng hash |
| `false` | `false` | Hợp lệ |

Cách nói thường dùng là **“equal objects must have equal hash codes”**, chứ không phải “equal hash codes mean equal objects”.

Điều này cũng có nghĩa là từ `a.hashCode() != b.hashCode()` có thể kết luận `a.equals(b)` **không thể** là `true` nếu cả hai lớp tuân thủ hợp đồng. Dù vậy, trong logic nghiệp vụ bạn vẫn nên dùng `equals()` khi câu hỏi thực sự là “hai đối tượng có bằng nhau hay không”.

Lưu ý điều kiện vận hành: so sánh và hash cần được xét trong trạng thái nhất quán của các đối tượng, theo hợp đồng `equals`/`hashCode`, thay vì giả định kết quả vẫn có nghĩa sau khi thay đổi các trường tham gia tính bằng nhau.

## 2. Vì sao trùng hash là điều không tránh khỏi?

`hashCode()` trả về một số kiểu `int`, tức giá trị 32-bit có dấu. Trong khi đó, số lượng chuỗi, tổ hợp trường và trạng thái đối tượng khác nhau có thể lớn hơn nhiều so với số giá trị `int` khả dụng. Vì vậy, **không thể gán một mã băm duy nhất cho mọi giá trị có thể có**.

Khi hai đối tượng khác nhau cho cùng kết quả từ hàm băm, ta gọi đó là **hash collision**. Một collision chỉ có nghĩa hai đối tượng cùng giá trị mã băm; nó **không tự chứng minh** hai đối tượng có cùng nội dung, cùng danh tính hay cùng ý nghĩa nghiệp vụ.

Ví dụ dễ hiểu: giả sử mã băm tưởng tượng chỉ là phần dư khi chia mã số khách hàng cho 10. Khách hàng số 21 và 31 đều có hash 1, nhưng họ vẫn là hai khách hàng khác nhau. Đây là ví dụ ý tưởng, không phải thuật toán của `Object.hashCode()` hay `HashMap`.

Ngay cả khi một lớp dùng hàm băm chất lượng tốt, collision vẫn có thể xảy ra. Chất lượng hash chủ yếu ảnh hưởng đến mức độ phân bố khóa và hiệu năng, **không thay đổi định nghĩa bằng nhau** của đối tượng.

## 3. Collision có thể tái hiện với `String`

`String.hashCode()` có thuật toán được đặc tả trong Java, dựa trên dãy đơn vị mã UTF-16. Hai chuỗi khác nhau hoàn toàn có thể tạo ra cùng số băm. Cặp `"FB"` và `"Ea"` là một ví dụ nổi tiếng:

```java
String first = "FB";
String second = "Ea";

System.out.println(first.hashCode());           // 2236
System.out.println(second.hashCode());          // 2236
System.out.println(first.hashCode()
        == second.hashCode());                   // true
System.out.println(first.equals(second));       // false
System.out.println(first == second);            // false
```

Đây là đoạn minh họa đặt trong một phương thức Java, không phải chương trình độc lập. `String.equals()` kiểm tra nội dung ký tự, vì thế `"FB"` và `"Ea"` không bằng nhau. Còn `==` trên hai tham chiếu hỏi có cùng đối tượng hay không; hai literal nội dung khác nhau này không trỏ cùng đối tượng. Hai kết quả hash bằng nhau **không can thiệp** vào hai phép so sánh đó.

Có thể tự tính kết quả hash theo công thức của `String` cho hai ký tự:

```text
"FB": 'F' = 70, 'B' = 66  → 70 × 31 + 66 = 2236
"Ea": 'E' = 69, 'a' = 97  → 69 × 31 + 97 = 2236
```

Hai cặp ký tự khác nhau nhưng cùng kết quả là collision hợp lệ của `String.hashCode()`. Không cần dùng `new String(...)` để tạo ví dụ này, cũng không cần dựa vào một môi trường JVM có cách phân bổ đối tượng đặc biệt.

**Điểm cần nhớ:** ngay cả mã băm của một lớp chuẩn như `String` cũng không dùng làm định danh độc nhất hay bằng chứng để khẳng định hai chuỗi bằng nhau.

## 4. Ví dụ Java 17+ hoàn chỉnh: hai đối tượng cùng hash nhưng không `equals`

Trong lớp `Customer` dưới đây, hai trường `id` và `name` cùng tham gia xác định bằng nhau. Tuy nhiên, `hashCode()` cố ý chỉ trả về mã băm của `id` để minh họa một trường hợp collision dễ dự đoán.

Đây là một cách cài đặt **hợp lệ về hợp đồng nhưng phân bố hash có thể kém** nếu nhiều khách hàng trùng `id`. Ở ứng dụng thực tế, thường nên tính hash từ đầy đủ các trường tham gia `equals` để giảm những collision không cần thiết.

Lưu tệp thành `HashCollisionDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCollisionDemo {
    static final class Customer {
        private final int id;
        private final String name;

        Customer(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return id == other.id
                    && Objects.equals(name, other.name);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Customer a = new Customer(7, "Lan");
        Customer b = new Customer(7, "Mai");
        Customer copyOfA = new Customer(7, "Lan");

        System.out.println("a hash: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("same hash a/b: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a equals copy: " + a.equals(copyOfA));
        System.out.println("same hash a/copy: "
                + (a.hashCode() == copyOfA.hashCode()));

        String first = "FB";
        String second = "Ea";
        System.out.println("string hashes: "
                + first.hashCode() + ", " + second.hashCode());
        System.out.println("string equals: " + first.equals(second));

        Set<Customer> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(copyOfA);
        System.out.println("set size: " + set.size());

        Map<Customer, String> map = new HashMap<>();
        map.put(a, "first");
        map.put(b, "second");
        System.out.println("map size: " + map.size());
        System.out.println("lookup by equal key: " + map.get(copyOfA));
        System.out.println("lookup colliding key: " + map.get(b));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac HashCollisionDemo.java
java HashCollisionDemo
```

Kết quả chính xác:

```text
a hash: 7
b hash: 7
same hash a/b: true
a equals b: false
a equals copy: true
same hash a/copy: true
string hashes: 2236, 2236
string equals: false
set size: 2
map size: 2
lookup by equal key: first
lookup colliding key: second
```

Giải thích:

1. `a` và `b` có cùng `id == 7` nên có cùng hash `7`, nhưng tên khác nhau, vì thế `a.equals(b)` là `false`.
2. `a` và `copyOfA` là hai đối tượng được tạo riêng. Dù `a == copyOfA` là `false`, `a.equals(copyOfA)` là `true` vì các trường tham gia `equals` có cùng giá trị; do đó hash của chúng bắt buộc bằng nhau.
3. `"FB"` và `"Ea"` có cùng hash `2236` nhưng khác nội dung nên `equals()` là `false`.
4. `HashSet` giữ `a` và `b` như hai phần tử khác nhau. `copyOfA` bằng `a` nên không tạo phần tử thứ ba.
5. `HashMap` lưu `a` và `b` như hai khóa khác nhau. Tra bằng `copyOfA` vẫn tìm được giá trị của `a` vì `copyOfA.equals(a)` là `true` và hash khớp.

Ví dụ in các phép tra cứu trực tiếp, không duyệt bộ sưu tập, nên không phụ thuộc thứ tự lặp của `HashMap` hoặc `HashSet`.

## 5. `HashMap` xử lý collision thế nào?

Có thể hình dung thao tác tra cứu bằng khóa `key` trong một cấu trúc dựa trên băm qua các bước khái niệm:

1. Lấy mã băm của khóa; cấu trúc có thể xử lý thêm các bit và ánh xạ đến vị trí lưu trữ.
2. Xác định nơi có thể chứa mục nhập cần tìm dựa vào mã băm.
3. Nếu nhiều khóa cùng rơi vào cùng vị trí, cấu trúc phải **phân biệt khóa** bằng kiểm tra tính bằng nhau, chứ không tự coi mọi khóa có cùng hash là một khóa.
4. Trả về mục nhập ứng với khóa bằng nhau, hoặc kết luận không có khóa phù hợp.

Đây là sơ đồ khái niệm, không phải mã nội bộ bắt buộc của mọi phiên bản triển khai `HashMap`:

```text
Khóa cần tra
    │
    ▼
Tính/đối chiếu hash
    │
    ▼
Xác định nhóm ứng viên
    │
    ▼
Đối chiếu khóa trong nhóm
    │
    ├─ equals == true  → cùng khóa logic
    │
    └─ equals == false → khóa khác, dù có thể cùng hash
```

Lưu ý kỹ hơn: triển khai `HashMap` của Java có thể dùng cả kiểm tra **cùng tham chiếu** (`==`) để nhận diện nhanh chính khóa đó, rồi mới gọi `equals()` khi cần. Chi tiết tổ chức bucket, danh sách hay cây là vấn đề triển khai và hiệu năng, không làm thay đổi quy tắc quan trọng: **chỉ trùng hash chưa đủ để coi hai khóa bằng nhau**.

Trong ví dụ, hai `Customer` có hash 7 vẫn cùng tồn tại trong `HashMap` vì `a.equals(b) == false`. Nếu bảng chỉ dùng hash làm bằng chứng duy nhất của bằng nhau, dữ liệu của `a` và `b` sẽ bị gộp sai.

`HashSet` dựa trên cơ chế băm và kiểm tra bằng nhau tương tự để xác định phần tử đã tồn tại. Vì vậy, hai phần tử có cùng hash nhưng `equals() == false` vẫn được thêm vào tập hợp.

## 6. Phân biệt collision hợp lệ và vi phạm hợp đồng

Hai lỗi suy luận thường bị lẫn với nhau.

### Trường hợp A — Collision hợp lệ

```text
a.equals(b) == false
a.hashCode() == b.hashCode()
```

Đây **không phải lỗi**. Bộ sưu tập vẫn phải phân biệt `a` và `b`. Số collision cao có thể ảnh hưởng hiệu năng, nhưng tự nó không chứng minh `equals()` hoặc `hashCode()` được viết sai.

### Trường hợp B — Vi phạm hợp đồng

```text
a.equals(b) == true
a.hashCode() != b.hashCode()
```

Đây là lỗi cài đặt thật sự. Khi hai khóa được đánh giá bằng nhau nhưng mã băm không khớp, cấu trúc dựa trên băm có thể tìm khóa ở những vị trí không tương thích, khiến `contains`, `get` hoặc thao tác thêm phần tử có kết quả trái mong đợi.

Ví dụ lỗi thiết kế (đoạn minh họa trong một lớp có trường `id` và `name`):

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id; // Chỉ id quyết định bằng nhau
}

@Override
public int hashCode() {
    return Objects.hashCode(name); // SAI: lại phụ thuộc name
}
```

Đoạn trên không phải chương trình độc lập. Nó chỉ ra một sai lầm: nếu hai `Customer` có cùng `id` nhưng `name` khác nhau, `equals()` cho `true` trong khi `hashCode()` có thể khác. Tham khảo như một **phản ví dụ**, không sao chép để dùng trong ứng dụng.

Trong một triển khai hợp lệ cho trường hợp chỉ `id` xác định tính bằng nhau, nên tính `hashCode` dựa trên `id`, chẳng hạn `Integer.hashCode(id)`. Khi cả `id` và `name` quyết định `equals`, cách tính `Objects.hash(id, name)` là lựa chọn tự nhiên hơn so với hash chỉ từ `id`.

## 7. Những yêu cầu thật sự của `hashCode()`

Ngoài chiều bắt buộc “`equals` bằng nhau ⇒ hash bằng nhau”, hợp đồng `hashCode()` còn yêu cầu:

- Với cùng đối tượng, khi không có thông tin nào dùng cho phép so sánh `equals` thay đổi, các lần gọi `hashCode()` trong một lần thực thi chương trình phải trả về giá trị nhất quán. Giá trị không bắt buộc giống nhau giữa các lần chạy riêng biệt của ứng dụng.
- Nếu `a.equals(b) == true`, chúng phải có cùng `hashCode()`.
- Nếu `a.equals(b) == false`, không bắt buộc mã băm khác nhau. **Phân biệt được nhiều hash hơn có thể giúp hiệu năng tốt hơn**, nhưng không phải điều kiện đúng/sai của hợp đồng.

Vì vậy, một cài đặt đơn giản như:

```java
@Override
public int hashCode() {
    return 1;
}
```

vẫn có thể **đúng hợp đồng** khi kết hợp với `equals()` hợp lệ và ổn định: mọi đối tượng đều có cùng hash, kể cả các đối tượng bằng nhau. Tuy nhiên, đây gần như luôn là một **lựa chọn hiệu năng tệ** khi nhiều đối tượng khác nhau cùng được đưa vào `HashMap`/`HashSet` vì tạo collision liên tục. Mục đích ví dụ là chứng minh “hash khác nhau” không phải yêu cầu cho các đối tượng không bằng nhau.

Ngược lại, `hashCode()` biến thiên ngẫu nhiên giữa những lần gọi trên cùng đối tượng không còn tuân thủ hợp đồng nhất quán và có thể làm bộ sưu tập băm hoạt động sai.

## 8. Nên dùng trường nào khi cài đặt?

Với lớp giá trị đơn giản có các trường bất biến:

```java
private final int id;
private final String name;

@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id && Objects.equals(name, other.name);
}

@Override
public int hashCode() {
    return Objects.hash(id, name);
}
```

Đây là các thành viên minh họa bên trong lớp `Customer`; `Objects` cần import `java.util.Objects` và mẫu `instanceof` sử dụng cú pháp được hỗ trợ trong Java 17.

**Quy tắc thực hành:** xác định trước tập trường nào tham gia `equals()` rồi tính hash theo cùng thông tin quan trọng ấy. `Objects.hash(id, name)` có lợi thế dễ đọc và giúp bảo đảm các đối tượng bằng nhau nhận cùng hash khi dữ liệu trường và hợp đồng của chúng đúng. Nó **không hứa hẹn** rằng các đối tượng khác nhau sẽ có hash khác nhau; collision vẫn có thể xảy ra.

Không cần các hàm `equals` và `hashCode` phải có cùng số phép so sánh hay tính toán. Điều quan trọng là mối quan hệ kết quả của chúng đúng. Trong ví dụ `Customer` đầu tiên, `equals` dùng cả `id` và `name` nhưng `hashCode` chỉ dùng `id` vẫn hợp lệ, vì khi hai đối tượng bằng nhau thì chắc chắn chúng có cùng `id`. Việc chỉ dùng ít trường hơn có thể làm tăng collision.

Không sử dụng `System.identityHashCode(obj)` để thay cho `hashCode()` theo nội dung ở lớp giá trị có `equals` tùy chỉnh: mã băm danh tính không được thiết kế để bảo đảm hai đối tượng có nội dung bằng nhau sẽ có hash giống nhau. Ngay cả mã băm danh tính cũng không được bảo đảm là duy nhất cho mỗi đối tượng.

### Trường dùng làm khóa cần ổn định

Nếu dùng đối tượng làm khóa của `HashMap` hoặc phần tử `HashSet`, cần đặc biệt thận trọng với những trường có thể sửa đổi mà lại tham gia `equals`/`hashCode`.

Giả sử một khóa được thêm vào `HashSet` khi có hash là 7. Sau đó chương trình sửa dữ liệu làm hash của chính khóa đó thành 8; thao tác `contains` có thể tra ở nhóm khác và không tìm được phần tử đang lưu. Đây là lỗi do **thay đổi trạng thái liên quan đến hash sau khi chèn**, không phải collision.

Ưu tiên đối tượng khóa bất biến hoặc quản lý vòng đời khóa sao cho các trường quyết định bằng nhau và hash không thay đổi trong lúc khóa nằm trong bộ sưu tập băm.

## 9. Những nhầm lẫn dễ gặp

1. **“Cùng hash là cùng đối tượng.”** Sai: `hashCode()` không phải địa chỉ hay ID duy nhất. Hai đối tượng khác nhau có thể nhận cùng hash.
2. **“Cùng hash thì `equals` luôn trả về `true`.”** Sai: `"FB"` và `"Ea"` đều có hash `2236` nhưng `String.equals` trả về `false`.
3. **“Hash collision làm `HashMap` ghi đè nhầm khóa.”** Sai đối với một `HashMap` hoạt động đúng và các khóa tuân thủ hợp đồng. Hai khóa khác nhau theo `equals` có thể cùng hash mà vẫn là hai mục nhập độc lập.
4. **“Hai đối tượng không bằng nhau bắt buộc hash khác nhau.”** Không có yêu cầu này trong hợp đồng.
5. **“Miễn `equals` đúng thì không cần quan tâm `hashCode`.”** Sai: `equals` bằng nhau bắt buộc kéo theo hash bằng nhau, đặc biệt khi làm việc với bộ sưu tập băm.
6. **“Tất cả khóa cùng hash nghĩa là chương trình sai.”** Không nhất thiết sai về logic, nhưng phân bố hash quá kém có thể làm giảm hiệu năng.
7. **“Một lần kiểm tra `hashCode` bằng nhau là đủ thay cho `equals`.”** Sai. Chỉ xem hash để thu hẹp ứng viên; dùng phép so sánh logic thích hợp để kết luận bằng nhau.
8. **“`Objects.hash(...)` tạo mã băm không bao giờ trùng.”** Sai. Đây là cách tiện lợi để xây dựng hash từ các trường, vẫn trả về một `int` với số lượng kết quả hữu hạn.

## 10. Tự kiểm tra

Hãy cho biết từng nhận định là **đúng** hay **sai**, rồi đối chiếu giải thích:

| Nhận định | Đáp án | Giải thích |
| --- | --- | --- |
| Nếu `x.equals(y)` là `true` thì `x.hashCode() == y.hashCode()`. | Đúng | Đây là chiều bắt buộc của hợp đồng. |
| Nếu `x.hashCode() == y.hashCode()` thì `x.equals(y)` phải là `true`. | Sai | Collision có thể xảy ra. |
| Nếu `x.hashCode() != y.hashCode()` thì `x.equals(y)` có thể `true` trong một lớp tuân thủ hợp đồng. | Sai | Bằng nhau phải kéo theo hash bằng nhau. |
| Hai `Customer` có cùng `id` nhưng khác `name` vẫn có thể cùng tồn tại trong `HashSet`, khi `equals` so sánh cả hai trường. | Đúng | Hash có thể trùng; `equals` phân biệt phần tử. |
| Ghi đè `hashCode()` luôn trả về 1 chắc chắn làm `equals()` sai. | Sai | Hash cố định vẫn đáp ứng chiều bắt buộc nhưng phân bố rất kém. |
| Dùng `Objects.hash(id, name)` bảo đảm mọi cặp `Customer` khác nhau đều có hash khác nhau. | Sai | Không có bảo đảm không collision. |

Thử tự sửa ví dụ `HashCollisionDemo`: đổi `hashCode()` của `Customer` sang `Objects.hash(id, name)` và chạy lại. Khi đó `a` và `copyOfA` vẫn phải cho hash bằng nhau; `a` và `b` có thể cho hash khác nhau. **Không lấy việc hash khác nhau của cặp cuối làm điều kiện đúng đắn**: phép `equals` và hợp đồng mới là nền tảng.

## Ghi nhớ

**`equals(a, b) == true` bắt buộc dẫn đến cùng `hashCode`; cùng `hashCode` không thể đảo ngược để suy ra `equals(a, b) == true`.** Collision là hiện tượng bình thường của hàm băm trả về `int`. `HashMap` và `HashSet` có cơ chế phân biệt những khóa/phần tử khác nhau dù chúng chung mã băm, miễn hợp đồng `equals`/`hashCode` của khóa được tuân thủ. Khi cần kết luận bằng nhau theo dữ liệu, hãy dựa trên `equals()` và hợp đồng của kiểu, không coi hash như danh tính hoặc dấu vân tay duy nhất.