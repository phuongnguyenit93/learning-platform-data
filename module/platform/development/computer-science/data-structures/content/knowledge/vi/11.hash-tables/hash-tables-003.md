# Điều kiện nhất quán giữa phép so sánh bằng nhau và hàm băm

## 1. Vì sao bảng băm cần cả phép so sánh và hàm băm?

Trong bảng băm (hash table), khóa dùng để định vị một giá trị, ví dụ mã sinh viên `"SV-007"` dùng để tìm hồ sơ. Một **hàm băm** tạo ra mã băm của khóa; bảng chuyển mã đó thành chỉ số ngăn. Khi nhiều khóa cùng ngăn, bảng vẫn phải **so sánh khóa** để tìm đúng bản ghi. Vì vậy, để thao tác thêm, tìm và cập nhật hoạt động chính xác, kết quả của hai cơ chế này phải tương thích.

Giả sử chương trình dùng:

- `equals(a, b)` hoặc `a == b` để trả lời: “Hai đối tượng có được xem là **cùng một khóa logic** không?”
- `hash(a)` để trả lời: “Mã băm của khóa `a` là gì?”
- `index(a) = hash(a) mod m` trong một cách tổ chức bảng đơn giản có `m > 0` ngăn.

**Quy tắc nền tảng:** Nếu hai khóa được xem là bằng nhau, chúng **bắt buộc phải có cùng mã băm** khi được xử lý bằng cùng quy tắc băm.

```text
Nếu a == b  thì  hash(a) == hash(b)      (BẮT BUỘC)

Nếu hash(a) == hash(b)  thì a == b        (KHÔNG SUY RA)
```

Quy tắc này còn được gọi là **hợp đồng giữa equality và hashing** (equality–hash contract). Nó là bất biến quan trọng của map và set dựa trên bảng băm. “Bằng nhau” ở đây được định nghĩa bởi cấu trúc hoặc kiểu khóa, không nhất thiết là hai biến tham chiếu đến cùng một đối tượng trong bộ nhớ.

## 2. Điều kiện bắt buộc và những điều không bắt buộc

| Kết quả so sánh | Quan hệ giữa mã băm | Hợp lệ? | Giải thích |
| --- | --- | --- | --- |
| `a == b` | `hash(a) == hash(b)` | **Bắt buộc** | Cùng khóa logic phải được định vị theo cùng quy tắc |
| `a == b` | `hash(a) != hash(b)` | **Sai hợp đồng** | Chương trình có thể tìm sai ngăn và bỏ sót khóa |
| `a != b` | `hash(a) == hash(b)` | **Được phép** | Va chạm mã băm; cần so sánh khóa để phân biệt |
| `a != b` | `hash(a) != hash(b)` | **Được phép** | Hai khóa có hai mã băm khác nhau |

Trong một bảng băm tuân thủ hợp đồng, từ `hash(a) != hash(b)` ta có thể kết luận `a != b` (phản đảo của điều kiện bắt buộc). Nhưng từ `hash(a) == hash(b)` tuyệt đối **không thể kết luận** `a == b`.

Ví dụ một hàm băm minh họa cho mã số sinh viên là `hash(k) = k mod 10`. Hai mã `21` và `31` khác nhau nhưng đều có mã băm là `1`. Không có lỗi nào trong việc băm hai khóa khác nhau về cùng một giá trị: bảng băm cần lưu thông tin khóa và so sánh chúng khi xảy ra va chạm.

## 3. Điều gì xảy ra nếu hai khóa bằng nhau có mã băm khác nhau?

Xét một bảng có 8 ngăn và hai đối tượng biểu diễn cùng mã sinh viên `"SV-9"`. Giả sử phép so sánh nói chúng bằng nhau, nhưng hàm băm sai lại trả về 10 cho đối tượng đầu và 13 cho đối tượng sau:

```text
equals(a, b) = true           Cùng một khóa logic

hash(a) = 10  ---> 10 mod 8 = 2  ---> ngăn 2: lưu (a, hồ_sơ)
hash(b) = 13  ---> 13 mod 8 = 5  ---> ngăn 5: tìm b ở đây
```

Chương trình đã lưu dữ liệu với khóa `a`, nhưng khi tìm bằng khóa `b`, nó đến ngăn 5 và có thể kết luận không tìm thấy. Hậu quả tùy cách cài đặt: `get(b)` bỏ sót dữ liệu, `put(b, giá_trị_mới)` tạo bản ghi có khóa logic trùng, hoặc `contains(b)` trả về `false` dù `a` đã tồn tại.

Ngay cả khi hai mã băm khác nhau **tình cờ** dẫn tới cùng chỉ số trong một bảng cụ thể, hợp đồng vẫn bị vi phạm. Khi bảng thay đổi kích thước, hoặc dùng cách ánh xạ khác, sự trùng chỉ số đó có thể biến mất.

Ngược lại, khi hai khóa **không bằng nhau** nhưng mã băm trùng, bảng chỉ cần giải quyết va chạm bằng nối chuỗi hoặc thăm dò phù hợp. Đây là hoạt động bình thường, không làm mất tính đúng đắn nếu chương trình vẫn kiểm tra khóa.

## 4. “Bằng nhau” phải có định nghĩa rõ ràng

Với số nguyên hoặc chuỗi thông thường, phép so sánh bằng nhau thường có sẵn. Nhưng khi khóa là một **đối tượng**, ta cần quyết định những thuộc tính nào xác định danh tính logic của khóa.

Ví dụ kiểu `SinhVien` gồm `ma_so` và `ten_hien_thi`. Nếu yêu cầu nghiệp vụ là “hai sinh viên có cùng mã số đại diện cùng một hồ sơ”, ta định nghĩa:

```text
equals(a, b) = (a.ma_so == b.ma_so)
hash(a)      = hash(a.ma_so)
```

Theo quy tắc này, tên hiển thị không tham gia cả so sánh lẫn tính mã băm. Nếu dùng `ma_so` để so sánh nhưng lại dùng `ten_hien_thi` để băm, hai đối tượng cùng mã số và tên khác nhau có thể vi phạm hợp đồng.

Một tình huống khác là khóa email được xem là không phân biệt chữ hoa/chữ thường theo **quy tắc cụ thể của ứng dụng**. Khi đó, nếu so sánh theo dạng chuẩn hóa `email.casefold()` thì hàm băm cũng phải dùng dạng chuẩn hóa ấy:

```text
equals(a, b) = (a.email.casefold() == b.email.casefold())
hash(a)      = hash(a.email.casefold())
```

Đây chỉ là ví dụ về chính sách so sánh do ứng dụng lựa chọn; không nên mặc định mọi hệ thống email đều dùng một quy tắc chuẩn hóa duy nhất. Điều cốt lõi là **cùng một định nghĩa danh tính** được áp dụng cho cả equality và hashing.

### Bản thân phép bằng nhau cũng cần nhất quán

Khi khóa được dùng như một phần tử của map hoặc set, quan hệ bằng nhau nên hoạt động như quan hệ tương đương:

1. **Phản xạ:** `a == a`.
2. **Đối xứng:** nếu `a == b` thì `b == a`.
3. **Bắc cầu:** nếu `a == b` và `b == c` thì `a == c`.
4. **Ổn định trong thời gian lưu:** nếu các thuộc tính tạo danh tính không đổi, kết quả so sánh phải nhất quán qua những lần kiểm tra.

Vi phạm các tính chất này có thể khiến một map không xác định được duy nhất đâu là “cùng khóa”, kể cả khi hàm băm có vẻ đúng.

## 5. Python: một kiểu khóa thực hiện đúng hợp đồng

Trong Python, `dict` và `set` dùng cả `__hash__` lẫn `__eq__` của đối tượng. Với khóa chỉ được xác định bởi `ma_so`, ta có thể dùng `dataclass` bất biến và loại `ten_hien_thi` khỏi phép so sánh:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KhoaSinhVien:
    ma_so: str
    ten_hien_thi: str = field(compare=False)


a = KhoaSinhVien("SV-9", "An")
b = KhoaSinhVien("SV-9", "Bình")
c = KhoaSinhVien("SV-10", "An")

print(a == b)               # True: cùng mã số
print(hash(a) == hash(b))   # True: băm từ các trường tham gia so sánh
print(a == c)               # False

ho_so = {a: {"diem": 9}}
print(ho_so[b])             # {'diem': 9}: tra cứu bằng khóa bằng nhau

ho_so[b] = {"diem": 10}
print(len(ho_so))           # 1: cập nhật cùng khóa logic
```

Ở đây, `frozen=True` ngăn thay đổi trực tiếp các trường của đối tượng sau khi khởi tạo. Theo cấu hình mặc định của `dataclass` này, `__eq__` và `__hash__` được sinh nhất quán từ trường tham gia so sánh là `ma_so`; trường `ten_hien_thi` có `compare=False` không ảnh hưởng đến danh tính logic. Vì `ma_so` là chuỗi bất biến, mã băm của khóa cũng ổn định trong vòng đời đối tượng.

Chú ý: `frozen=True` không tự làm bất biến những **đối tượng có thể thay đổi nằm bên trong** một trường; với khóa phức tạp cần chọn hoặc sao chép dữ liệu tham gia băm sao cho chúng không bị biến đổi ngoài ý muốn.

### Ví dụ cố ý sai: so sánh theo mã, băm theo tên

```python
class KhoaSai:
    def __init__(self, ma_so, ten):
        self.ma_so = ma_so
        self.ten = ten

    def __eq__(self, other):
        return isinstance(other, KhoaSai) and self.ma_so == other.ma_so

    def __hash__(self):
        return len(self.ten)  # SAI: tên không nằm trong điều kiện bằng nhau


x = KhoaSai("SV-9", "An")
y = KhoaSai("SV-9", "Binh")

print(x == y)               # True
print(hash(x), hash(y))     # 2 4: VI PHẠM hợp đồng
```

Mặc dù `x == y`, mã băm khác nhau vì trường `ten` có độ dài khác nhau. Đây là lỗi thiết kế khóa. Cách sửa là để `__hash__` băm đúng những thuộc tính xác định bình đẳng, ví dụ `return hash(self.ma_so)`, và giữ `ma_so` bất biến khi đối tượng nằm trong `dict` hoặc `set`.

Python còn có một cơ chế bảo vệ: nếu lớp tự định nghĩa `__eq__` mà không định nghĩa `__hash__` phù hợp, Python thường đặt `__hash__ = None` cho lớp đó. Đối tượng sẽ **không dùng được làm khóa của `dict`** cho đến khi có chính sách băm phù hợp, thay vì tự động kế thừa một mã băm có thể không tương thích.

## 6. Java: `equals()` và `hashCode()` phải đi cùng nhau

Trong Java, `HashMap` và `HashSet` dựa vào hợp đồng giữa `equals()` và `hashCode()`. Một kiểu khóa cho mã sinh viên có thể được cài đặt như sau:

```java
import java.util.Objects;

final class MaSinhVien {
    private final String ma;

    MaSinhVien(String ma) {
        this.ma = Objects.requireNonNull(ma);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof MaSinhVien)) return false;
        MaSinhVien other = (MaSinhVien) obj;
        return ma.equals(other.ma);
    }

    @Override
    public int hashCode() {
        return ma.hashCode();
    }
}
```

Hai thể hiện `MaSinhVien("SV-9")` là hai đối tượng riêng nhưng `equals()` trả `true` và `hashCode()` phải bằng nhau vì cùng dùng trường `ma`. Nếu chỉ ghi đè `equals()` mà quên `hashCode()`, lớp có thể dùng mã băm không phù hợp với khái niệm bằng nhau mới, khiến `HashMap` không tìm đúng bản ghi.

Java còn yêu cầu `hashCode()` trả về cùng kết quả trong những lần gọi khi thông tin tham gia phép so sánh `equals()` không đổi trong cùng một lần thực thi; không bắt buộc giữ cùng mã băm qua những lần chạy chương trình khác nhau. Đây cũng là lý do dùng khóa có trường định danh bất biến thường dễ bảo đảm tính đúng đắn hơn.

## 7. Tính ổn định của khóa sau khi đưa vào bảng

Giả sử ban đầu đối tượng `k` được lưu trong bảng với `hash(k) = 21`. Nếu sau đó ai đó thay đổi trường tạo danh tính khiến `hash(k) = 34`, lần tra cứu tiếp theo có thể bắt đầu tại ngăn khác và không tìm thấy mục đã lưu.

```text
Thời điểm thêm:   k.ma_so = "SV-21" --> hash = 21 --> ngăn cũ
Sau khi sửa:      k.ma_so = "SV-34" --> hash = 34 --> ngăn mới
                                                       khác ngăn cũ
```

Kể cả khi thay đổi đồng thời cả `__eq__` và `__hash__` theo một công thức tương thích, **thay đổi trạng thái của khóa đang lưu** vẫn gây vấn đề: bảng không tự biết rằng khóa cần được chuyển vị trí. Để đổi danh tính logic, cách an toàn thường là xóa mục bằng khóa cũ rồi thêm khóa mới (theo thao tác của cấu trúc đang dùng).

Một phân biệt hữu ích: **bằng nhau** quy định hai đối tượng biểu diễn cùng khóa; **mã băm** hỗ trợ định vị nhanh khóa; **chỉ số ngăn** còn phụ thuộc kích thước và quy tắc tổ chức bảng. Bảng có thể mở rộng, khiến chỉ số thay đổi và phải phân bố lại dữ liệu, nhưng điều kiện “khóa bằng nhau → mã băm bằng nhau” vẫn phải được bảo toàn.

## 8. Tự kiểm tra

**Câu 1.** Có hai khóa `a` và `b` với `a == b`, nhưng `hash(a) = 7` và `hash(b) = 9`. Tình huống này có hợp lệ không?

**Đáp án:** Không. Nó vi phạm hợp đồng giữa phép bằng nhau và hàm băm. Các thao tác tìm hoặc cập nhật có thể chọn những vị trí khác nhau cho cùng khóa logic.

**Câu 2.** Hai khóa khác nhau có mã băm bằng nhau. Có phải hàm băm bị lỗi và bắt buộc sửa để hai mã khác nhau?

**Đáp án:** Không. Va chạm có thể xảy ra ngay cả với hàm băm tốt. Điều cần thiết là bảng xử lý va chạm và so sánh khóa chính xác.

**Câu 3.** Một lớp `NguoiDung` xem hai người dùng bằng nhau nếu cùng `id`, dù `ten` khác nhau. Nên băm thuộc tính nào?

**Đáp án:** Nên băm giá trị `id` (hoặc một biểu diễn ổn định tương đương được xác định từ `id`). Không nên băm `ten` nếu tên không tham gia quy tắc bằng nhau.

**Câu 4.** Một đối tượng dùng làm khóa được phép sửa `id` sau khi thêm vào `HashMap` nếu `equals` và `hashCode` đều dùng `id`?

**Đáp án:** Không nên. Sửa `id` có thể làm mã băm hoặc quan hệ bằng nhau thay đổi trong lúc bản ghi vẫn ở vị trí cũ, dẫn tới tra cứu sai. Nên dùng định danh bất biến hoặc xóa rồi thêm khóa mới.

**Câu 5.** Hai khóa có `hash(a) == hash(b)`. Có thể bỏ qua `equals(a, b)` khi tìm kiếm không?

**Đáp án:** Không. Hai khóa khác nhau vẫn có thể cùng mã băm; việc so sánh khóa giúp phân biệt chúng khi va chạm.

**Ghi nhớ:** Quy tắc không thể thiếu của bảng băm là **`a == b` kéo theo `hash(a) == hash(b)`**. Chiều ngược lại không đúng. Phải dùng một định nghĩa danh tính logic nhất quán, giữ khóa ổn định trong thời gian lưu và luôn kiểm tra bằng nhau khi có va chạm để việc thêm, tìm, cập nhật, xóa hoạt động chính xác.
