# Bộ duyệt nhất quán yếu, bộ duyệt ảnh chụp và phát hiện sửa đổi

## 1. Vấn đề: đang duyệt thì một luồng khác sửa dữ liệu

Giả sử nền tảng học tập lưu danh sách những học viên đã đăng ký. Luồng **T1** đang duyệt danh sách để lập báo cáo; cùng lúc luồng **T2** thêm một học viên mới và xóa một đăng ký bị hủy.

Trong chương trình chỉ có một luồng, ta thường hình dung:

```text
Danh sách ban đầu: [A, B, C]

Duyệt:
  lấy A
  lấy B
  lấy C
```

Khi có cập nhật đồng thời, câu hỏi không chỉ là “có phát sinh lỗi hay không”:

- Bộ duyệt có **bắt buộc** trả đúng A, B, C như lúc bắt đầu?
- Nếu T2 thêm D, T1 có được phép nhìn thấy D không?
- Nếu T2 xóa B trước khi T1 đến lượt B, T1 có trả B nữa không?
- Bộ duyệt có được phép báo lỗi vì cấu trúc thay đổi không?
- Nếu không báo lỗi, kết quả có phải là một **ảnh chụp nhất quán tại một thời điểm** không?

Đó là lý do phải phân biệt ba hợp đồng:

1. **Bộ duyệt nhất quán yếu (weakly consistent iterator):** cho phép duyệt trong khi dữ liệu thay đổi, nhưng không cam kết kết quả là một ảnh chụp cố định.
2. **Bộ duyệt ảnh chụp (snapshot iterator):** cố định một phiên bản dữ liệu và duyệt trên phiên bản đó, độc lập với các sửa đổi về sau.
3. **Bộ duyệt phát hiện sửa đổi (fail-fast/modification-detecting iterator):** theo dõi dấu hiệu thay đổi và có thể từ chối tiếp tục khi cấu trúc không còn đúng với kỳ vọng.

Các cơ chế này giải quyết **những nhu cầu khác nhau**. “Không ném lỗi” không đồng nghĩa “đã nhìn thấy toàn bộ dữ liệu”; “có phát hiện sửa đổi” không đồng nghĩa “đã đồng bộ an toàn”; và “ảnh chụp” cũng không đồng nghĩa “dữ liệu mới nhất khi xử lý xong”.

Bài thuộc chương **Truy cập đồng thời** trong nền tảng **Cấu trúc dữ liệu**, nơi hiểu **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** quyết định cách chọn collection phù hợp.

## 2. Bộ duyệt là gì, và điều gì làm nó khó khi đồng thời?

Một **iterator** là đối tượng hoặc giao diện trả dần các phần tử, thường bằng các thao tác:

```text
iterator = collection.iterator()
iterator.has_next()
iterator.next()
```

Trong Python, giao diện tương ứng là `iter(collection)` và `next(iterator)`; trong Java thường là `Iterator.hasNext()/next()`.

Iterator có thể giữ trạng thái nội bộ:

- **Vị trí hiện tại:** chỉ số trong mảng, con trỏ nút kế tiếp, vị trí bucket, hoặc khóa cuối đã đọc.
- **Thông tin cấu trúc:** phiên bản bảng băm, độ dài danh sách, offset của vùng dữ liệu.
- **Nguồn dữ liệu:** tham chiếu đến collection đang sống, bản copy, hoặc handle của một phiên bản bất biến.

Nếu luồng khác thêm/xóa phần tử, những thông tin này có thể **không còn khớp** với trạng thái hiện hành.

### Ví dụ xóa phần tử trong mảng

```text
Ban đầu:
index   0   1   2   3
value   A   B   C   D
             ↑
         iterator vừa đọc B,
         cursor chuẩn bị đến index 2

Luồng khác xóa A, các phần tử dịch trái:
index   0   1   2
value   B   C   D

Nếu iterator cứ đọc index 2, nó sẽ trả D và có thể bỏ qua C.
```

Đây là **một lịch minh họa**, không phải hành vi được bảo đảm của mọi ngôn ngữ hoặc collection. Một iterator dùng con trỏ, một iterator có kiểm tra phiên bản và một iterator giữ bản snapshot sẽ xử lý khác nhau.

**Bất biến của collection** (ví dụ mảng có độ dài hợp lệ, bảng băm tra được mọi khóa đang tồn tại) không tự bảo đảm **bất biến của thuật toán duyệt** (ví dụ mỗi phần tử của một thời điểm được xử lý đúng một lần).

## 3. Ba hợp đồng, ba câu trả lời cho cùng một câu hỏi

Giả sử dữ liệu ban đầu là `{A,C}`. Iterator được tạo; sau đó luồng khác thêm B, xóa C.

| Câu hỏi | Nhất quán yếu | Ảnh chụp | Phát hiện sửa đổi |
| --- | --- | --- | --- |
| Có thể duyệt khi writer cập nhật? | Có, theo hợp đồng của collection | Có, nếu snapshot đã được tạo/công bố an toàn | Có thể ném lỗi khi iterator kiểm tra thay đổi |
| B có thể xuất hiện không? | Có thể, không mặc nhiên bảo đảm | Không, nếu B thêm **sau** thời điểm chụp | Không có đầu ra đầy đủ đáng tin sau khi sửa đổi |
| C đã bị xóa có thể vẫn xuất hiện không? | Tùy thời điểm và cài đặt | Có, nếu C nằm trong snapshot | Có thể phát hiện thay đổi trước khi trả tiếp |
| Tất cả mục trả về thuộc cùng một phiên bản? | **Không cam kết** | **Có**, nếu snapshot thực sự nhất quán và dữ liệu bất biến theo hợp đồng | **Không tự cam kết** nếu chỉ kiểm tra version ở vài thời điểm |
| Mục tiêu chính | Duyệt có ích giữa những cập nhật | Ảnh nhìn ổn định | Phát hiện sử dụng iterator không phù hợp |
| Chi phí điển hình | Phụ thuộc cách thực hiện | Sao chép/giữ phiên bản và quản lý vòng đời | Kiểm tra bộ đếm sửa đổi |

**Đừng nhầm tên gọi với bảo đảm:** thuật ngữ “fail-safe iterator” đôi khi xuất hiện trong tài liệu không chính thức để chỉ bộ duyệt không ném lỗi. Nhưng **không ném lỗi không nói lên tính nhất quán**. Hãy dùng các mô tả chính xác hơn như *weakly consistent* hoặc *snapshot*.

## 4. Bộ duyệt nhất quán yếu: nhìn một phần của trạng thái đang thay đổi

Một **weakly consistent iterator** thường cho phép writer cập nhật collection trong khi iterator đang đọc, không ném lỗi chỉ vì có thay đổi cấu trúc. Nó có thể quan sát **một phần** các cập nhật xảy ra sau khi được tạo.

Ví dụ:

```text
Ban đầu: A, C
T1: tạo iterator
T1: lấy A
T2: thêm B
T2: xóa C
T1: lấy B
T1: kết thúc
```

Dòng kết quả `A,B` có thể phù hợp với một bộ duyệt nhất quán yếu: A có trước, B được thêm khi đang duyệt và C đã bị xóa trước khi được đọc.

Một cài đặt khác có thể trả `A,C` hoặc chỉ `A`, tùy cách iterator duyệt các vùng dữ liệu và chính sách của collection. **Không suy ra một quy tắc cụ thể từ tên “weakly consistent”**; phải đọc hợp đồng của thư viện.

### Điều gì được bảo đảm?

Ở mức khái quát:

- Hoạt động duyệt được thiết kế để **tương tác an toàn với cập nhật đồng thời**, thay vì truy cập tùy tiện một bộ nhớ đang bị sửa.
- Không coi mỗi thay đổi sau lúc tạo iterator là lỗi bắt buộc.
- **Không đòi** kết quả phải là tập phần tử của đúng một thời điểm duy nhất.
- Việc có thấy mục mới hay mục vừa bị xóa phụ thuộc **hợp đồng cụ thể và lịch xen kẽ**.

Không được hứa rằng mọi iterator nhất quán yếu đều **không bao giờ lặp phần tử**, luôn trả **tất cả phần tử có mặt khi bắt đầu**, hoặc luôn thấy **mọi phần tử thêm sau đó**. Một thư viện có thể có những bảo đảm cụ thể mạnh hơn; ta chỉ dùng được khi chúng được công bố.

### Ứng dụng

Duyệt một bảng trạng thái lớn để lập **số liệu tham khảo gần đúng**, kiểm tra sức khỏe hệ thống, quét tìm công việc có thể lặp lại, hoặc liệt kê một danh sách **không bắt buộc phản ánh đúng một snapshot** là những tình huống có thể chấp nhận mức nhất quán yếu.

**Không nên dùng trực tiếp** kết quả ấy để tính tổng tiền phải đối soát, xuất snapshot phục vụ kiểm toán, quyết định quota chính xác, hoặc chứng minh BFS đã thăm đủ tất cả đỉnh của một phiên bản đồ thị.

## 5. Bộ duyệt ảnh chụp: kết quả thuộc một phiên bản cố định

Một **snapshot iterator** duyệt một trạng thái `S_t` đã được cố định tại một thời điểm logic `t`.

```text
Thời gian       t0           t1           t2
                |------------|------------|
T1: snapshot    [A, C]
T2:                          thêm B
T2:                                       xóa C

T1 duyệt snapshot:
                A ----------------------> C
```

Trong ví dụ, iterator vẫn trả A và C; nó **không tự thêm B** dù B đã xuất hiện trong collection hiện hành sau `t0`.

### Hai cách tạo snapshot phổ biến

**Sao chép dữ liệu (copy snapshot)**

```text
lock(collection)
    frozen = copy(collection)
unlock(collection)

for item in frozen:
    xử lý(item)
```

**Giữ phiên bản bất biến (versioned/immutable snapshot)**

```text
writer xây V2 từ V1 → công bố V2
reader R1 giữ handle của V1
reader R2 giữ handle của V2
```

Với sao chép, thời gian tạo và bộ nhớ thường tăng theo kích thước dữ liệu. Với cấu trúc bất biến/persistent, nhiều phiên bản có thể dùng chung các phần **thực sự bất biến**, nhưng phải quản lý tham chiếu và việc thu hồi phiên bản cũ.

### Snapshot phải nhất quán ngay khi tạo

Chỉ gọi `copy(collection)` không tự bảo đảm một snapshot hợp lệ nếu writer đang sửa collection. Nếu cần ảnh chụp **của cả cấu trúc tại một thời điểm logic**, quá trình copy phải:

- Nắm khóa tương thích với **mọi writer liên quan**; hoặc
- Đọc một **phiên bản đã công bố hoàn chỉnh và bất biến**; hoặc
- Dùng giao thức snapshot/transaction/phiên bản khác có bảo đảm tương đương.

Sao chép một `dict` tại thời điểm các writer đang sửa ba chỉ mục của đồ thị có thể cho kết quả **mỗi chỉ mục thuộc một phiên bản khác nhau**, nếu thiếu giao thức đồng bộ.

### Sao chép nông và phần tử mutable

```python
rows = [{"id": "A", "score": 10}]
shallow = list(rows)
rows[0]["score"] = 99
print(shallow[0]["score"])  # 99: phần tử dict vẫn được dùng chung.
```

`list(rows)` chỉ sao chép **các tham chiếu phần tử**. Nếu mục tiêu là snapshot **giá trị**, có thể cần đối tượng bất biến, deep copy có kiểm soát hoặc phiên bản hóa cả phần tử.

**Snapshot của tập tham chiếu** và **snapshot của toàn bộ trạng thái sâu** là hai hợp đồng khác nhau. Một iterator giữ bản copy của danh sách khóa vẫn có thể thấy **giá trị mới** nếu mỗi lần đọc giá trị đều tra lại map hiện hành.

## 6. Bộ duyệt phát hiện sửa đổi: fail-fast và bộ đếm phiên bản

Một cách tiếp cận khác: iterator ghi nhớ dấu hiệu sửa đổi tại lúc tạo, rồi so sánh mỗi khi lấy phần tử.

```text
collection.mod_count = 5

T1: iterator.expected_mod_count = 5
T1: next() → trả A

T2: thêm B
    collection.mod_count = 6

T1: next()
    expected 5 != actual 6
    → ném lỗi "collection đã được sửa"
```

Trong Java, ví dụ quen thuộc là iterator của `ArrayList`: các thay đổi **cấu trúc** bên ngoài cơ chế iterator có thể dẫn tới `ConcurrentModificationException`. Tuy nhiên, **cơ chế fail-fast của Java chỉ là best-effort**, không phải một bảo đảm để thiết kế giao thức đồng bộ.

Một số API phân biệt:

- **Thay đổi cấu trúc:** thêm/xóa phần tử, đổi chiều dài hoặc làm iterator mất giả định về bố trí.
- **Thay đổi giá trị:** thay thuộc tính của phần tử hoặc gán lại một giá trị mà không đổi số mục.

Việc thay đổi nào làm tăng `mod_count` **phụ thuộc collection**. Không nên mặc định mọi kiểu sửa đều được phát hiện.

### Fail-fast không phải “an toàn luồng”

Bộ đếm sửa đổi là **cơ chế báo động sử dụng sai iterator**, không phải khóa bảo vệ dữ liệu. Khi hai luồng sửa/duyệt không đồng bộ:

- Iterator có thể ném lỗi trước khi tiếp tục.
- Nó cũng có thể **không phát hiện đúng lúc** hoặc không phát hiện được một lịch cụ thể.
- Cơ chế mod-count đơn giản không tự cung cấp quy tắc **nhìn thấy bộ nhớ** cho người đọc.
- Báo lỗi **sau khi đã xử lý vài mục** không tự hoàn tác tác dụng phụ của những mục đã xử lý.

Ngay cả khi một iterator chắc chắn phát hiện sửa đổi, điều đó không có nghĩa thao tác duyệt đã tạo một snapshot hay một giao dịch nguyên tử.

### Fail-fast có thể xảy ra trong cùng một luồng

```text
iterator = list.iterator()
iterator.next()        # A
list.add(B)            # Sửa cấu trúc qua collection
iterator.next()        # Có thể ném lỗi fail-fast
```

Không cần một luồng thứ hai để tạo tình huống này. Một số collection hỗ trợ `iterator.remove()` và tự cập nhật bộ đếm kỳ vọng khi xóa **qua chính iterator**; phải theo đúng hợp đồng của API cụ thể.

## 7. Ví dụ Java: ba loại hợp đồng trong thư viện

Đoạn mã sau minh họa ba họ collection thường gặp trong Java. Đây là **ví dụ tham khảo API**, không phải một quy tắc áp dụng cho mọi danh sách/map của mọi runtime.

### `ConcurrentHashMap`: bộ duyệt nhất quán yếu

```java
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

Map<String, Integer> marks = new ConcurrentHashMap<>();
marks.put("A", 10);
marks.put("C", 30);

Iterator<Map.Entry<String, Integer>> it =
    marks.entrySet().iterator();

marks.put("B", 20);   // Sửa sau khi đã tạo iterator.

while (it.hasNext()) {
    Map.Entry<String, Integer> entry = it.next();
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Iterator của `ConcurrentHashMap` có cơ chế **weak consistency**, không dùng `ConcurrentModificationException` như một tín hiệu thông thường cho những cập nhật đồng thời. **Không thể dự đoán từ mã trên rằng B chắc chắn được in ra**; hành vi nhìn các cập nhật mới phụ thuộc lúc duyệt và triển khai.

Không dùng vòng lặp này để kết luận tổng các giá trị là **tổng tại một thời điểm duy nhất** nếu có writer chạy đồng thời.

### `CopyOnWriteArrayList`: bộ duyệt ảnh chụp

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

CopyOnWriteArrayList<String> names =
    new CopyOnWriteArrayList<>(Arrays.asList("A", "C"));

Iterator<String> it = names.iterator();
names.add("B");  // Tạo bản mảng mới, iterator cũ giữ ảnh chụp cũ.

while (it.hasNext()) {
    System.out.println(it.next());  // A, C
}
```

Iterator của `CopyOnWriteArrayList` đọc **bản mảng cố định** tại thời điểm iterator được tạo. Các thao tác sửa đổi tạo bản dữ liệu mới, nên iterator cũ không thấy B. Đổi lại, nhiều cập nhật có thể phải sao chép đáng kể dữ liệu.

### `ArrayList`: phát hiện sửa đổi, không phải cơ chế đồng bộ

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

List<String> names =
    new ArrayList<>(Arrays.asList("A", "C"));

Iterator<String> it = names.iterator();
names.add("B");  // Sửa cấu trúc không qua iterator.

System.out.println(it.next());
// Có thể gặp ConcurrentModificationException.
```

`ArrayList` không tự là collection an toàn luồng. Fail-fast **không** được dùng thay cho mutex hay snapshot khi có nhiều luồng.

## 8. Python: bộ duyệt từ danh sách và dict cần hiểu đúng

Trong Python, không nên đồng nhất hành vi của `list` và `dict`:

```python
items = ["A", "B", "C"]
it = iter(items)
print(next(it))  # A
items.insert(0, "X")
print(next(it))  # Có thể là A vì phần tử bị dịch vị trí.
```

Trong những triển khai Python phổ biến, iterator của list có thể tiếp tục theo chỉ số hiện tại khi list thay đổi. Nhưng điều này **không biến list thành concurrent collection an toàn**, và không nên dựa vào hành vi tình cờ để lập báo cáo chính xác.

Với dict:

```python
marks = {"A": 10, "B": 20}
it = iter(marks)
print(next(it))
marks["C"] = 30

# next(it) có thể ném RuntimeError do kích thước dict đổi.
```

Một `RuntimeError` trong trường hợp này **không phải** hợp đồng “fail-fast đủ mạnh để đồng bộ mọi lịch chạy đa luồng”. Việc thay giá trị tại một khóa đã tồn tại có thể không thay kích thước dict và có thể không bị phát hiện theo cùng cách.

**Khuyến nghị:** nếu cần duyệt nhất quán trong môi trường có writer, dùng `Lock` cùng giao thức, snapshot bất biến hoặc một cấu trúc concurrent được thiết kế rõ ràng cho mục đích đó.

## 9. Bài toán xuyên suốt: một danh mục và ba cách duyệt

Ta viết một lớp Python **minh họa** với các yêu cầu có thể kiểm tra:

- ID là chuỗi không rỗng; giá trị là **int**, được xem là bất biến.
- Dữ liệu trong `_data` và thứ tự khóa trong `_keys` được bảo vệ bởi **cùng một Lock**.
- `_revision` tăng khi thêm/xóa **hoặc gán giá trị**, kể cả cập nhật khóa đã tồn tại.
- `iter_snapshot()` sao chép các cặp `(ID,value)` thành tuple khi đang giữ lock.
- `iter_fail_fast()` ghi nhớ `_revision` lúc tạo; mỗi lần `next()` kiểm tra lại dưới lock.
- `iter_weak()` mỗi lần gọi `next()` tìm **khóa kế tiếp lớn hơn khóa cuối đã trả**, dưới một lock ngắn, và có thể thấy một số khóa mới.

**Đây là một cài đặt giáo dục**, không phải sao chép cơ chế trong Java. Hợp đồng cụ thể của iterator yếu ở đây **mạnh hơn ở một vài chi tiết**: khóa trả ra theo thứ tự tăng, mỗi ID trả nhiều nhất một lần, và khóa mới được thêm **phía sau cursor** có thể xuất hiện nếu thêm trước lúc iterator kết thúc. Các bảo đảm ấy chỉ đến từ thiết kế của mẫu này, **không tự áp dụng cho mọi weakly consistent iterator**.

## 10. Cài đặt Python: snapshot, fail-fast, weak trên cùng dữ liệu

Mẫu dùng Python 3.10+ và các kiểu dữ liệu đơn giản, không gọi tác vụ mạng hay cho phép mã ngoài sửa trực tiếp dữ liệu nội bộ.

```python
from bisect import bisect_left, bisect_right, insort
from threading import Lock


class DanhMuc:
    def __init__(self):
        self._lock = Lock()
        self._data = {}       # ID -> int
        self._keys = []       # Danh sách ID có thứ tự tăng.
        self._revision = 0    # Tăng với mọi lần ghi thành công.

    def upsert(self, key: str, value: int):
        if type(key) is not str or not key:
            raise ValueError("ID phải là chuỗi không rỗng")
        if type(value) is not int:
            raise ValueError("Giá trị phải là số nguyên")

        with self._lock:
            if key not in self._data:
                insort(self._keys, key)
            self._data[key] = value
            self._revision += 1

    def remove(self, key: str) -> bool:
        with self._lock:
            if key not in self._data:
                return False
            del self._data[key]
            i = bisect_left(self._keys, key)
            self._keys.pop(i)
            self._revision += 1
            return True

    def snapshot(self):
        with self._lock:
            return tuple((k, self._data[k]) for k in self._keys)

    def iter_snapshot(self):
        # Iterator được tạo từ tuple cố định, không tra lại map sống.
        return iter(self.snapshot())

    def iter_fail_fast(self):
        # Chụp revision ngay khi khởi tạo iterator,
        # không trì hoãn tới lần next đầu tiên của generator.
        with self._lock:
            expected = self._revision
        return FailFastIterator(self, expected)

    def iter_weak(self):
        return WeakIterator(self)


class FailFastIterator:
    def __init__(self, catalog: DanhMuc, expected: int):
        self._catalog = catalog
        self._expected = expected
        self._index = 0
        self._finished = False

    def __iter__(self):
        return self

    def __next__(self):
        # Sau StopIteration, iterator luôn ở trạng thái kết thúc.
        if self._finished:
            raise StopIteration
        c = self._catalog
        with c._lock:
            if c._revision != self._expected:
                raise RuntimeError("Danh mục đã thay đổi sau khi tạo iterator")
            if self._index >= len(c._keys):
                self._finished = True
                raise StopIteration
            key = c._keys[self._index]
            self._index += 1
            return key, c._data[key]


class WeakIterator:
    def __init__(self, catalog: DanhMuc):
        self._catalog = catalog
        self._last = None
        self._finished = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._finished:
            raise StopIteration

        c = self._catalog
        with c._lock:
            # Mỗi next() có một cửa sổ đọc riêng trên map sống.
            i = (0 if self._last is None
                 else bisect_right(c._keys, self._last))
            if i == len(c._keys):
                self._finished = True
                raise StopIteration

            key = c._keys[i]
            self._last = key
            return key, c._data[key]


d = DanhMuc()
d.upsert("A", 10)
d.upsert("C", 30)

snapshot_it = d.iter_snapshot()
failfast_it = d.iter_fail_fast()
weak_it = d.iter_weak()

print(next(snapshot_it))  # ('A', 10)
print(next(failfast_it))  # ('A', 10)
print(next(weak_it))      # ('A', 10)

# Xen kẽ có chủ đích: thêm khóa B, sửa rồi xóa khóa C.
d.upsert("B", 20)
d.upsert("C", 300)
d.remove("C")

print(list(snapshot_it))  # [('C', 30)] — dữ liệu tại lúc chụp.

try:
    print(next(failfast_it))
except RuntimeError as error:
    print("FAIL_FAST:", str(error))
    # FAIL_FAST: Danh mục đã thay đổi sau khi tạo iterator.

print(list(weak_it))  # [('B', 20)] — thấy B mới, không thấy C đã xóa.
print(d.snapshot())   # (('A', 10), ('B', 20))
```

### Đọc đúng ba kết quả

**Snapshot:** được tạo lúc `_data={A:10,C:30}`. Sau khi A đã được duyệt, phần còn lại luôn là `C=30`, bất kể C bị đổi thành 300 rồi xóa khỏi collection sống.

**Fail-fast:** iterator nhớ `revision` cũ. Khi T2 giả lập thêm B, thay C rồi xóa C, `revision` đã thay đổi; lần `next()` tiếp theo nhận `RuntimeError` trước khi cố dùng chỉ số cũ.

**Weak:** sau khi trả A, cursor là `"A"`. Lần `next()` sau tra `bisect_right` để lấy khóa **lớn hơn A** trong bảng hiện tại: B đã thêm, còn C đã xóa, nên trả B. Nó **không phản ánh snapshot** `{A,C}` lúc đầu, cũng không tuyên bố đã duyệt đủ những khóa tồn tại trong bất kỳ thời điểm nào.

### Khi có thêm phần tử phía trước cursor

Nếu iterator yếu đã trả B, rồi writer chèn khóa `"AA"` (nhỏ hơn B theo thứ tự chuỗi), bộ duyệt trong ví dụ **không quay lại** để trả AA. Đó là một phần rõ ràng của hợp đồng ví dụ: đi **một chiều theo thứ tự ID**, không phải “phát hiện mọi thay đổi”.

**Lưu ý về mức đồng thời:** đoạn demo xen kẽ các lời gọi **tuần tự có chủ đích** để kết quả tái lập. Khi dùng hai luồng thật, khóa ngắn trong `__next__` bảo vệ từng bước đọc; thứ tự lên lịch của writer có thể làm đầu ra weak khác, đúng với ý nghĩa yếu của nó.

## 11. Phân tích chi phí của ví dụ Python

Gọi `n` là số khóa đang hoạt động, `r` là số mục iterator thực sự trả ra.

| Công việc | Chi phí công việc, chưa tính chờ Lock |
| --- | --- |
| Tạo `iter_snapshot()` | `O(n)` thời gian, `O(n)` bộ nhớ cho tuple/các cặp |
| Duyệt phần còn lại của snapshot | `O(r)` thời gian, `O(1)` bộ nhớ phụ của iterator |
| Tạo `iter_fail_fast()` | `O(1)` thời gian/bộ nhớ cho trạng thái iterator |
| Mỗi `next()` của fail-fast | `O(1)` kỳ vọng cho lookup dict và truy cập list |
| Tạo `iter_weak()` | `O(1)` |
| Mỗi `next()` của weak trong **ví dụ này** | `O(\log n)` do `bisect_right` và `O(1)` kỳ vọng để tra giá trị |
| Thêm ID mới vào `_keys` đã sắp | `O(n)` vì `insort` có thể phải dời các mục |
| Xóa ID khỏi `_keys` | `O(n)` vì `pop(i)` phải dời các mục |
| Sửa giá trị của ID đã tồn tại | `O(1)` kỳ vọng cho cập nhật dict, chưa tính khóa |

Bộ nhớ của bản danh mục là `O(n)` cho map và danh sách ID; mỗi snapshot được giữ sống cần thêm `O(n)` mục tham chiếu/cặp trong trường hợp này.

Không nên lấy chi phí `O(\log n)` của **iterator yếu minh họa** để gán cho iterator của `ConcurrentHashMap`. Cấu trúc lưu và cơ chế duyệt khác nhau nên chi phí khác nhau. Cũng không nên kết luận mọi snapshot đều phải deep-copy từng phần tử: với phiên bản bất biến có **chia sẻ cấu trúc**, số byte sao chép có thể khác đáng kể.

**Thời gian chờ khóa** không nằm trong Big-O công việc. Một snapshot giữ lock để sao chép `n` mục có thể làm writer chờ lâu hơn so với một lần `next()` chỉ giữ lock ngắn; ngược lại, quá nhiều lần lấy/nhả lock cũng tạo overhead.

## 12. Kết quả weak không tự là tập dữ liệu của một thời điểm

Xét một trường hợp tổng quát với danh mục có hai mục A và B:

```text
Tại t0: A=10, B=90, tổng=100

T1 đọc A=10
T2 chuyển 20 từ B sang A như một giao dịch:
    A=30, B=70, tổng vẫn 100
T1 đọc B=70

T1 tính tổng = 80.
```

Mỗi giá trị T1 đọc có thể hợp lệ **tại một thời điểm riêng**, nhưng tổng 80 **không phải tổng của một snapshot nhất quán**. Một iterator yếu có thể cung cấp kết quả tương tự, ngay cả khi cấu trúc không bị hỏng và mỗi `next()` an toàn riêng lẻ.

Đây là sự khác nhau giữa:

- **An toàn từng bước đọc:** không quan sát trạng thái nội bộ sai khi lấy một mục.
- **Nhất quán xuyên suốt lượt duyệt:** mọi mục và thuộc tính tương ứng với **một phiên bản logic**.

Muốn tính tổng chính xác, phải có một thao tác `sum`/`snapshot` được đồng bộ phù hợp hoặc hệ thống phiên bản có thể đọc **cùng một revision** của toàn bộ dữ liệu.

**Lưu ý:** ngay cả khi không có writer, một iterator có thể chỉ trả **một phần** dữ liệu do logic lọc, giới hạn trang hoặc lỗi nghiệp vụ. Không được đồng nhất “weakly consistent” với nguyên nhân duy nhất dẫn tới thiếu mục.

## 13. Duyệt an toàn bằng khóa suốt lượt: lựa chọn thứ tư

Một cách bảo đảm lượt duyệt trên dữ liệu không đổi là **giữ cùng lock suốt quá trình đọc**:

```python
with catalog_lock:
    for item in shared_collection:
        process(item)
```

Nếu mọi writer đều dùng `catalog_lock`, người đọc sẽ thấy dữ liệu không bị writer sửa trong lúc duyệt. Nhưng cách này có chi phí và rủi ro:

- Nếu `process(item)` gọi mạng, ghi tệp, ngủ hoặc gọi callback không tin cậy, lock có thể bị giữ **rất lâu**.
- Writer khác phải chờ toàn bộ quá trình duyệt; có thể tăng p95/p99 latency.
- Callback có thể gọi ngược vào collection và gây **deadlock**, đặc biệt nếu lock không tái nhập.
- Nếu một ngoại lệ xảy ra, `with` nhả lock đúng, nhưng các **tác dụng phụ đã thực hiện** không tự rollback.

Một cách thường tốt hơn cho báo cáo là:

```python
with catalog_lock:
    frozen = tuple(shared_collection)

for item in frozen:
    process(item)
```

Với **giá trị bất biến** và mọi đường đọc/ghi tuân thủ lock, ta giữ khóa trong thời gian `O(n)` sao chép rồi xử lý lâu bên ngoài lock. Khi `process` dùng đối tượng mutable, cần snapshot giá trị đúng độ sâu như đã nói.

**Không viết generator giữ lock khi `yield` trong vòng lặp** mà không chủ ý về vòng đời: generator có thể tạm dừng ở `yield` nhưng vẫn **giữ lock**, làm những luồng khác phải chờ cho tới khi người dùng duyệt tiếp hoặc đóng generator.

## 14. Snapshot khi có nhiều chỉ mục: ví dụ đồ thị

Xét đồ thị có hướng lưu:

```text
vertices                 tập đỉnh
edges[eid] = (source, target)
out[source]               danh sách/set edge ID đi ra
incoming[target]          danh sách/set edge ID đi vào
```

Bất biến khi đã công bố:

\[
e=(u\to v)\in E
\Longrightarrow e\in out[u]\;\land\;e\in incoming[v].
\]

Nếu writer thêm một cung rồi cập nhật lần lượt bảng `edges`, `out`, `incoming`, một iterator trực tiếp duyệt `out` trong lúc iterator khác duyệt `incoming` có thể thấy **hai kết quả khác phiên bản**.

Với đồ thị có **khuyên** `u→u`, cùng một ID xuất hiện ở cả out/in của u; với **cung song song**, hai ID khác nhau có thể nối cùng nguồn–đích. Không được gộp chúng chỉ theo cặp đầu mút khi xuất snapshot của đa đồ thị.

### Một snapshot đồ thị nhất quán

```python
from threading import Lock


class DoThiCoAnhChup:
    def __init__(self, vertices):
        self._lock = Lock()
        self._vertices = set(vertices)
        self._edges = {}       # eid -> (u, v)
        self._out = {v: set() for v in self._vertices}
        self._incoming = {v: set() for v in self._vertices}
        self._next_eid = 0
        self._version = 0

    def add_arc(self, u, v):
        with self._lock:
            if u not in self._vertices or v not in self._vertices:
                raise KeyError("Đỉnh nguồn/đích không tồn tại")
            eid = self._next_eid
            self._next_eid += 1
            self._edges[eid] = (u, v)
            self._out[u].add(eid)
            self._incoming[v].add(eid)
            self._version += 1
            return eid

    def snapshot(self):
        # Bảng cạnh chuẩn và danh mục V được chụp dưới CÙNG lock.
        with self._lock:
            return (
                self._version,
                frozenset(self._vertices),
                tuple(
                    (eid, u, v)
                    for eid, (u, v) in self._edges.items()
                ),
            )


g = DoThiCoAnhChup(["A", "B", "C", "D"])
e0 = g.add_arc("A", "B")
e1 = g.add_arc("A", "B")  # Cung song song.
e2 = g.add_arc("B", "B")  # Khuyên.
before = g.snapshot()

e3 = g.add_arc("B", "C")
after = g.snapshot()

assert before[0] == 3 and after[0] == 4
assert len(before[1]) == 4        # Gồm D cô lập.
assert len(before[2]) == 3        # e0, e1, e2.
assert len(after[2]) == 4         # Có thêm e3.
assert e3 not in {eid for eid, _, _ in before[2]}
```

Vì dữ liệu snapshot chỉ gồm `int`, `str`, `tuple` và `frozenset`, người đọc có thể duyệt bản sao đó ngoài lock mà không bị cập nhật vào `_edges` ảnh hưởng. **Không cần xuất ba bảng cùng lúc** nếu ta chọn bảng cạnh chuẩn để dựng lại chỉ mục từ snapshot.

**Giới hạn:** ví dụ minh họa cập nhật trong bộ nhớ, chưa có rollback nếu xảy ra lỗi tài nguyên giữa các bước cập nhật. Bất kỳ mã nào sửa trực tiếp các thuộc tính nội bộ bỏ qua `_lock` đều phá hợp đồng.

## 15. BFS/DFS trên đồ thị đang thay đổi: đúng với đồ thị nào?

BFS từ A cần duyệt những cung đi ra để xác định tập đỉnh tới được.

```text
Snapshot V1:
A → B → C

T1: BFS(V1) bắt đầu, thăm A
T2: xóa B→C, thêm A→D
T1: tiếp tục đọc đồ thị sống
```

Nếu T1 đọc các cung ra của A **trước** cập nhật, nhưng đọc cung ra của B **sau** cập nhật, T1 có thể:

- Không tới C vì B→C đã bị xóa.
- Không tới D vì đã xử lý A trước lúc A→D được thêm.

Kết quả có thể **không phải tập reachable** của V1 **lẫn** V2. Ngay cả khi từng lượt đọc danh sách kề an toàn, BFS hoàn chỉnh không tự là một thao tác **snapshot-consistent**.

### Ba cách thiết kế tùy yêu cầu

1. **BFS trên snapshot:** chụp V và E ở một phiên bản, dựng danh sách kề rồi duyệt. Kết quả đúng **theo phiên bản đó**, có thể đã cũ khi trả về.
2. **BFS có kiểm tra phiên bản:** chụp phiên bản, duyệt theo giao thức đọc an toàn, kiểm tra lại phiên bản; nếu đổi, từ chối kết quả và thử lại khi được phép. Chỉ kiểm tra số phiên bản **không tự thay thế** việc bảo vệ những bước truy cập nội bộ.
3. **BFS nhất quán yếu:** chấp nhận thay đổi đang diễn ra; thích hợp với một số thuật toán tìm kiếm gần đúng/giám sát, nhưng phải **định nghĩa rõ** kết quả có ý nghĩa gì và có cần xử lý lại khi đồ thị thay đổi không.

BFS/DFS theo danh sách kề trên **một snapshot cố định** tốn `O(n+m)` cho duyệt toàn đồ thị; tạo snapshot và dựng chỉ mục cũng thường cần `O(n+m)` công việc và bộ nhớ phụ nếu sao chép đầy đủ.

**Không nên** tự tuyên bố BFS trên iterator yếu vẫn có bất biến “mọi đỉnh tới được đều được thăm” nếu khái niệm “tới được” không gắn với một phiên bản đồ thị cụ thể.

## 16. Snapshot phiên bản và thuật toán phát hiện sửa đổi

Một giải pháp phổ biến là **optimistic validation**: đọc phiên bản trước, làm việc, sau đó kiểm tra xem phiên bản có thay đổi hay không.

```text
loop:
    (version, snapshot) = take_consistent_snapshot()
    result = compute(snapshot)
    if version_is_acceptable_for_result(version):
        return result
    retry
```

Nếu `compute` chỉ dùng snapshot bất biến, kết quả **luôn nhất quán với snapshot**, ngay cả khi writer đã đổi dữ liệu hiện hành. Kiểm tra version cuối chỉ cần thiết khi hợp đồng yêu cầu **không trả kết quả dựa trên một phiên bản đã cũ**.

Ngược lại, nếu thuật toán đọc **dữ liệu mutable sống** bằng nhiều bước, một cách “đọc version đầu/cuối” ngây thơ có thể nguy hiểm:

```text
v1 = version                 # đọc không đồng bộ
for item in mutable_data:    # writer có thể sửa cấu trúc
    process(item)
v2 = version
if v1 == v2:
    accept_result()
```

Điều này **không mặc nhiên an toàn**:

- Iterator có thể đã truy cập nút bị xóa hoặc mảng đang resize **trước khi** kiểm tra cuối.
- Writer có thể làm thay đổi và lại khôi phục dữ liệu/phiên bản do **wraparound** hoặc quy tắc tăng version không đủ mạnh.
- Không có bảo đảm visibility/memory ordering phù hợp, hai lần đọc version có thể không chứng minh tính nhất quán của những trường khác.
- `process` có thể đã gửi email hoặc thay dữ liệu ngoài trước khi nhận ra kết quả phải bỏ.

Các thuật toán chuyên biệt như **seqlock** hoặc MVCC có quy tắc đọc/ghi, bộ đếm phiên bản, công bố bộ nhớ và chính sách retry rõ ràng. Không nên mô phỏng chúng chỉ bằng một số nguyên thường và hai lần `if`.

## 17. Bộ duyệt phát hiện sửa đổi: khi nào là lợi ích, khi nào là gánh nặng?

Một iterator fail-fast hữu ích khi:

- Cấu trúc mặc định được sử dụng theo cách **tuần tự hoặc độc quyền**.
- Sửa collection trong lúc duyệt thường là **lỗi lập trình**.
- Muốn nhận tín hiệu sớm thay vì âm thầm bỏ sót mục sau khi xóa/chèn.

Nhưng cần hiểu các giới hạn:

1. Phát hiện sửa đổi **không làm cấu trúc tự an toàn luồng**.
2. Lỗi xuất hiện sau khi đã xử lý một phần dữ liệu; nếu có tác dụng phụ, phải quyết định cách hoàn tác/tiếp tục.
3. Phạm vi phát hiện phụ thuộc **chính sách mod-count**: chỉ thay đổi cấu trúc hay cả thay đổi giá trị.
4. Kiểm tra có thể chỉ xảy ra trong `next()`, không phải ở mọi `hasNext()`.
5. Nếu không đồng bộ, fail-fast kiểu best-effort có thể **không phát hiện mọi lịch xen kẽ**.

### Những trường hợp thất bại hợp lệ

Nếu người dùng muốn sửa cấu trúc khi duyệt, có thể:

- Dùng thao tác `iterator.remove()` theo hợp đồng của collection hỗ trợ nó.
- Gom các thay đổi vào danh sách lệnh, duyệt xong mới áp dụng.
- Duyệt một snapshot.
- Chọn collection/iterator nhất quán yếu nếu kết quả yếu là chấp nhận được.

Không nên chỉ **bắt và bỏ qua** lỗi thay đổi, rồi kết luận rằng mọi phần tử đã được xử lý đúng.

## 18. Bộ duyệt ảnh chụp: quản lý bộ nhớ, phiên bản và tính cập nhật

Snapshot thường là lựa chọn dễ lý luận nhất cho báo cáo, xuất dữ liệu hoặc thuật toán cần trạng thái cố định. Nhưng chi phí cần tính:

### Sao chép toàn bộ

Nếu danh sách có `n` phần tử, việc tạo một `tuple` chứa n giá trị/tham chiếu cần `O(n)` thời gian và `O(n)` bộ nhớ cho mỗi ảnh chụp. Nếu mỗi phút tạo nhiều ảnh chụp cho hàng triệu phần tử, có thể tốn RAM và tăng áp lực cấp phát.

### Copy-on-write

Một số cấu trúc lưu bản mảng bất biến hiện tại; writer muốn thay đổi tạo bản mới rồi công bố. Iterator giữ bản cũ, nên bước tạo iterator thường nhẹ, **nhưng một lần thêm/xóa có thể phải sao chép `O(n)`**.

### Persistent structure/MVCC

Các phiên bản có thể chia sẻ phần cấu trúc thực sự bất biến. Reader giữ handle của một phiên bản; writer tạo phiên bản mới. Chi phí phụ thuộc cấu trúc và thao tác cụ thể, không thể mặc định sao chép `O(1)` cho mọi sửa đổi.

Một vấn đề khác là **giữ phiên bản cũ quá lâu**: iterator chưa kết thúc có thể khiến một mảng lớn hoặc nhiều node phiên bản cũ không được thu hồi. Tùy runtime, cần cơ chế reference count, GC, epoch hoặc quy tắc đóng handle.

### Tính cập nhật

Snapshot phản ánh một thời điểm đã chọn. Khi báo cáo hoàn tất sau vài phút, nó có thể **lạc hậu** so với collection sống. Nếu cần dữ liệu mới nhất tại một điểm giao dịch, phải định nghĩa thời điểm chụp và cơ chế xác thực, không chỉ chọn snapshot vì nó không lỗi khi duyệt.

## 19. So sánh độ phức tạp tổng quát

Bảng sau giả định một collection kích thước `n`, trả `r` mục. **“Thường”** là cách mô tả mô hình phổ biến, không phải cam kết cho mọi thư viện.

| Kiểu duyệt | Tạo iterator | Duyệt r mục | Bộ nhớ giữ thêm | Cập nhật của writer |
| --- | --- | --- | --- | --- |
| Nhất quán yếu trên concurrent hash/linked structure | Có thể `O(1)` | Có thể `O(r)` hoặc phụ thuộc quét bucket | Thường trạng thái cursor/metadata nhỏ | Chi phí đồng bộ theo cấu trúc, có thể có retry/resize |
| Snapshot bằng **sao chép n mục** | `O(n)` | `O(r)` | `O(n)` cho mỗi bản sao | Thường cập nhật bản gốc theo cách bình thường |
| Snapshot kiểu **copy-on-write array** | Thường `O(1)` để lấy handle bản mảng | `O(r)` | Giữ bản mảng cũ đang còn sống | Mỗi lần sửa có thể `O(n)` |
| Snapshot từ persistent structure | Phụ thuộc cách chụp/giữ version | Phụ thuộc cấu trúc | Có thể chia sẻ các node bất biến | Phụ thuộc đường sửa, quản lý phiên bản |
| Fail-fast với counter và list index | `O(1)` | `O(r)` nếu mỗi `next` là `O(1)` | `O(1)` | Thêm chi phí cập nhật mod-count |
| Giữ mutex xuyên suốt lượt duyệt | Thường `O(1)` để bắt đầu | `O(r)` | Không cần bản sao | Writer có thể phải **chờ cả lượt** |

**Tách ba loại chi phí:**

- **Công việc thuật toán:** số mục/bucket được kiểm tra, sao chép và xử lý.
- **Đồng bộ:** lấy/nhả lock, retry, công bố phiên bản, chờ writer/reader khác.
- **Vòng đời dữ liệu:** giữ snapshot, copy-on-write, GC, giải phóng nút cũ.

Một thao tác `O(1)` bước làm việc vẫn có thể mất thời gian đồng hồ rất lâu khi chờ một lock nóng hoặc khi iterator bị tạm dừng. Trong thực tế, hãy đo **latency p95/p99, thời gian giữ lock, số lần retry, số snapshot sống và bộ nhớ đỉnh**.

## 20. Chọn kiểu duyệt theo nhu cầu ứng dụng

| Nhu cầu | Lựa chọn thường phù hợp | Câu hỏi phải xác minh |
| --- | --- | --- |
| Quét gần đúng danh sách trạng thái đang thay đổi | **Weakly consistent** | Có chấp nhận bỏ sót hoặc nhìn một phần thay đổi không? |
| Xuất báo cáo nhất quán để đối soát | **Snapshot nhất quán** | Các giá trị có bất biến sâu, các chỉ mục cùng phiên bản không? |
| Duyệt rồi xử lý tính toán dài | **Snapshot** hoặc versioned view | Snapshot có thể cũ không, chi phí giữ phiên bản bao nhiêu? |
| Collection bình thường, muốn phát hiện lập trình viên sửa trong khi duyệt | **Fail-fast** | Có chấp nhận báo lỗi và khởi động lại công việc không? |
| Thêm/xóa liên tục, nhiều reader ngắn | **Concurrent structure với weak iterator** hoặc mô hình khác có hợp đồng rõ | Tần suất cập nhật, nội dung trả về và mức nhất quán cần thiết? |
| Nhiều đọc, rất ít ghi, dữ liệu không quá lớn | **Copy-on-write snapshot** | Có chấp nhận `O(n)` công việc cho mỗi lần sửa? |
| BFS/DFS cần kết quả tương ứng một đồ thị xác định | **Graph snapshot** | Phiên bản V/E được chụp đồng bộ và giữ ID/khuyên/cung song song? |
| Làm sạch dữ liệu theo từng mục nhưng có writer | **API thao tác nguyên tử từng mục** hoặc snapshot + kiểm tra lại | Mục có thể đổi giữa lúc đọc và lúc cập nhật không? |

Ví dụ **xóa các mục hết hạn**: duyệt snapshot để lấy danh sách ứng viên, rồi dùng một API `remove_if_still_expired(id, expected_version)` để xóa từng mục có điều kiện. Snapshot giúp chọn ứng viên ổn định; thao tác xóa có điều kiện giúp quyết định **vẫn đúng tại thời điểm cập nhật**.

Đó là cách phối hợp **nhất quán để đọc** và **nguyên tử để ghi**, thay vì lầm tưởng một iterator tốt tự bảo vệ mọi hành động nghiệp vụ sau khi đọc.

## 21. Kiểm thử: lịch xen kẽ và bất biến kết quả

Kiểm thử iterator đồng thời cần hơn một lời khẳng định “không ném exception”.

### 21.1. Tạo lịch có chủ đích

Với dữ liệu ban đầu A,C:

1. Tạo ba iterator.
2. Gọi `next` lần đầu cho mỗi iterator.
3. Thêm B và xóa C.
4. Gọi `next` tiếp, ghi rõ đầu ra hoặc lỗi.
5. So kết quả với **hợp đồng riêng của từng iterator**.

Ví dụ ở mục 10 thực hiện đúng thứ tự này, nên dễ hiểu hơn một stress test dựa vào lịch hệ điều hành ngẫu nhiên.

### 21.2. Kiểm tra điều kiện đúng theo từng loại

**Snapshot:**

- Kết quả phải bằng dữ liệu đã chụp, theo thứ tự đã định.
- Cập nhật sau khi tạo snapshot không thay đổi giá trị đã chụp.
- Với đối tượng mutable, kiểm tra cả việc snapshot có chia sẻ phần tử hay không.

**Fail-fast minh họa:**

- Nếu revision thay đổi, lần `next` tiếp theo phải nhận lỗi.
- Việc lấy iterator không làm khóa bị giữ mãi.
- Không dùng kết quả đã trả trước lỗi như một giao dịch đã hoàn thành.

**Weak minh họa:**

- Mỗi ID trả tối đa một lần.
- Thứ tự ID tăng nghiêm ngặt.
- Không trả khóa đã xóa trước thời điểm `next` của nó lấy lock.
- Khóa mới có thứ tự **lớn hơn cursor** có thể được nhìn thấy.
- Một khi kết thúc, iterator không sống lại chỉ vì writer thêm mục mới.

**Weak trong thư viện:** thay các điều kiện minh họa bằng **hợp đồng thật** của thư viện, không bê nguyên các cam kết này sang mọi `ConcurrentHashMap` hoặc bộ duyệt khác.

### 21.3. Test tiến triển

- Nhiều reader duyệt trong khi writer thêm/xóa liên tục.
- Một iterator bị dừng lâu; writer có bị giữ lock hoặc giữ version cũ lâu không?
- Bộ duyệt báo lỗi rồi code gọi retry: có khả năng **retry vô hạn** khi tranh chấp không?
- Một collection liên tục thay đổi có làm thuật toán “duyệt hết” không bao giờ kết thúc không?
- Snapshot rất lớn có gây tăng độ trễ writer hoặc áp lực RAM bất thường không?

**Stress test không phải bằng chứng hình thức.** Với cấu trúc tự triển khai, có thể cần race detector, kiểm tra lịch sử tuyến tính hóa hoặc kiểm chứng mô hình bộ nhớ ở mức phù hợp.

## 22. Những lỗi thường gặp

1. **“Iterator không ném lỗi nghĩa là nó duyệt một snapshot.”** Sai: weakly consistent iterator có thể trộn kết quả từ nhiều thời điểm.
2. **“Weakly consistent luôn nhìn thấy mọi phần tử thêm trong lúc duyệt.”** Không có cam kết tổng quát như vậy.
3. **“Weakly consistent luôn bỏ qua mọi phần tử đã xóa.”** Tùy thời điểm và cách cài; phần tử có thể đã được đọc trước khi xóa.
4. **“Mọi iterator yếu đều trả đúng một lần mỗi ID.”** Không suy ra nếu hợp đồng không ghi rõ.
5. **“Tạo list copy là snapshot sâu của các object.”** Sai: list mới có thể dùng chung các phần tử mutable.
6. **“Snapshot được tạo bằng copy không cần lock.”** Sai nếu writer có thể sửa dữ liệu trong lúc copy mà không có giao thức đọc phiên bản an toàn.
7. **“Snapshot luôn là trạng thái mới nhất khi xử lý xong.”** Sai: nó chỉ phản ánh phiên bản đã chụp.
8. **“Fail-fast là cơ chế đồng bộ an toàn luồng.”** Sai: mod-count là cơ chế phát hiện lỗi sử dụng, không thay thế memory synchronization.
9. **“Fail-fast luôn ném lỗi ngay khi có writer.”** Không, thường phải đến điểm kiểm tra, và có thư viện best-effort.
10. **“Không có exception nghĩa là không có thay đổi.”** Sai: sửa giá trị không làm tăng mod-count theo một số hợp đồng, hoặc không được phát hiện.
11. **“Chỉ những thay đổi từ luồng khác mới làm fail-fast.”** Sai: sửa ngay trong cùng luồng qua collection cũng có thể gây lỗi.
12. **“Bắt và bỏ qua lỗi fail-fast là tiếp tục duyệt an toàn.”** Không có bảo đảm đã xử lý đủ phần tử, và tác dụng phụ có thể dang dở.
13. **“Python list/dict có iterator nên tự an toàn khi luồng khác sửa.”** Không; cần đồng bộ hoặc đọc từ snapshot theo hợp đồng.
14. **“BFS dùng iterator an toàn từng bước thì kết quả đúng với một snapshot.”** Không: các danh sách kề có thể thuộc nhiều phiên bản.
15. **“Chụp bảng cung và bảng đỉnh ở hai thời điểm khác nhau vẫn là một graph snapshot.”** Có thể tạo cạnh mồ côi hoặc bỏ sót đỉnh/cung.
16. **“Copy-on-write làm mọi ghi thành `O(1)` vì đọc snapshot rẻ.”** Sai: ghi có thể cần sao chép cả mảng.
17. **“Iterator snapshot không tốn RAM nếu dữ liệu bất biến.”** Không nhất thiết; snapshot copy vẫn chiếm bộ nhớ, versioned view cũng giữ tài nguyên cũ.
18. **“Kiểm tra version đầu/cuối đủ an toàn cho mọi loại dữ liệu mutable.”** Sai: còn vấn đề memory visibility, lifetime và truy cập khi writer sửa.
19. **“Một phép đọc an toàn thì tổng nhiều phép đọc tự nhất quán.”** Sai: phải đọc từ cùng phiên bản.
20. **“Có GIL là đủ để mọi vòng `for` trên Python collection không bị sửa xen kẽ.”** Không có hợp đồng tổng quát như vậy.
21. **“Iterator fail-fast phát hiện mọi thay đổi trong mọi lịch chạy.”** Không, đặc biệt với cơ chế best-effort thiếu đồng bộ.
22. **“Duyệt xong là mọi mục được xử lý đúng một lần nghiệp vụ.”** Không: còn retry, tác dụng phụ, thay đổi nguồn và chính sách collection.

## 23. Tự kiểm tra

**Câu 1.** Bộ duyệt yếu được tạo khi danh mục có A và C; sau đó B được thêm. Có bắt buộc bộ duyệt yếu trả B không?

**Đáp án:** Không. Nó **có thể** thấy một phần cập nhật mới nhưng không có bảo đảm chung rằng sẽ thấy B. Phải đọc hợp đồng iterator cụ thể.

**Câu 2.** Một snapshot được chụp khi dữ liệu có A và C. Sau đó C bị xóa khỏi bản sống. Snapshot có còn được phép trả C không?

**Đáp án:** Có, vì snapshot phản ánh **phiên bản tại lúc chụp** và không thay đổi theo bản sống, giả sử cả dữ liệu phần tử được giữ ổn định theo hợp đồng.

**Câu 3.** `list(rows)` với `rows` là danh sách các dict mutable có bảo đảm snapshot giá trị sâu không?

**Đáp án:** Không. Nó sao chép danh sách chứa tham chiếu tới các dict cũ; sửa dict gốc vẫn có thể xuất hiện ở bản sao.

**Câu 4.** Cơ chế `mod_count` thường dùng để làm gì?

**Đáp án:** Ghi dấu hiệu thay đổi collection; một fail-fast iterator giữ bản `expected_mod_count` rồi so sánh tại các bước kiểm tra để báo lỗi khi phát hiện sự thay đổi không được phép.

**Câu 5.** Có thể dùng `ConcurrentModificationException` của `ArrayList` như một cơ chế an toàn đa luồng không?

**Đáp án:** Không. Cơ chế fail-fast chỉ là **best-effort**, không thay thế khóa hoặc một collection được thiết kế thread-safe.

**Câu 6.** Trong Java, iterator của `ConcurrentHashMap` và `CopyOnWriteArrayList` khác nhau ở ý nào?

**Đáp án:** Iterator của `ConcurrentHashMap` là **nhất quán yếu**, có thể nhìn một phần cập nhật; iterator của `CopyOnWriteArrayList` giữ **bản mảng ảnh chụp** tại lúc tạo và không thấy phần tử thêm sau.

**Câu 7.** Trong mã Python, vì sao `iter_fail_fast()` chụp `_revision` ngay khi gọi hàm tạo iterator, không trì hoãn bằng một generator thuần?

**Đáp án:** Vì thân generator chỉ chạy khi gọi `next()` lần đầu. Nếu revision được chụp muộn, một sửa đổi **giữa lúc tạo iterator và lúc gọi next** có thể bị bỏ qua trái hợp đồng dự định.

**Câu 8.** Bộ duyệt yếu minh họa đã trả A rồi người khác thêm B và xóa C. Tại sao `list(weak_it)` còn lại là `[("B",20)]`?

**Đáp án:** Iterator tìm khóa kế tiếp **lớn hơn A** trong danh mục hiện hành dưới lock. B đã xuất hiện, C đã xóa, nên chỉ còn B.

**Câu 9.** Nếu iterator yếu minh họa đã trả B, writer thêm khóa AA (nhỏ hơn B), iterator có quay lại trả AA không?

**Đáp án:** Không. Nó đi theo cursor khóa **tăng dần**, chỉ xét khóa lớn hơn khóa đã trả.

**Câu 10.** Bộ duyệt ảnh chụp bằng copy `n` cặp dữ liệu cần chi phí tạo và bộ nhớ thế nào?

**Đáp án:** Thường `O(n)` thời gian và `O(n)` bộ nhớ cho bản copy; duyệt `r` mục sau đó cần `O(r)` công việc.

**Câu 11.** Trong ví dụ Python, `next()` của iterator yếu có chi phí bao nhiêu nếu dùng `bisect_right`?

**Đáp án:** `O(\log n)` cho tìm chỉ số kế tiếp trong danh sách ID sắp xếp, cộng `O(1)` kỳ vọng để lấy giá trị từ dict; chưa tính thời gian chờ khóa.

**Câu 12.** Một BFS đọc danh sách kề của A trước khi thêm A→D, rồi đọc B sau khi xóa B→C. Kết quả có chắc là BFS của đồ thị trước hoặc sau cập nhật không?

**Đáp án:** Không. Nó có thể bỏ qua cả C lẫn D, trộn hai phiên bản; cần snapshot hoặc hợp đồng nhất quán khác để khẳng định kết quả.

**Câu 13.** Tại sao không nên trả một generator `yield` từng mục trong khi vẫn giữ `Lock` suốt vòng lặp?

**Đáp án:** Generator có thể **tạm dừng ở yield nhưng tiếp tục giữ lock**, khiến writer bị chặn cho tới khi người dùng duyệt tiếp hoặc đóng generator.

**Câu 14.** Bản ảnh chụp V1 và trạng thái hiện hành V2 khác nhau. Tính toán trên V1 có sai không?

**Đáp án:** Không nhất thiết. Nó có thể **đúng với V1** và chỉ **không mới nhất**; hợp đồng nghiệp vụ quyết định có được trả kết quả cũ hay phải tính lại.

**Câu 15.** Fail-fast iterator đã trả 10 mục rồi phát hiện sửa đổi. Hệ thống có được mặc định rằng 10 tác dụng phụ đã thực hiện sẽ tự hoàn tác không?

**Đáp án:** Không. Fail-fast chỉ báo lỗi; cần giao dịch, idempotency hoặc chính sách xử lý một phần riêng nếu tác dụng phụ phải nhất quán.

**Câu 16.** Muốn xóa những khóa hết hạn trong lúc hệ thống có writer, tại sao duyệt snapshot rồi `remove_if_still_expired` có thể tốt hơn “duyệt rồi xóa mù”?

**Đáp án:** Snapshot chọn ứng viên từ một trạng thái ổn định, còn thao tác xóa có điều kiện **kiểm tra lại tiền điều kiện tại thời điểm cập nhật**. Nếu mục được gia hạn sau snapshot, nó không bị xóa nhầm.

**Câu 17.** Một bộ duyệt không ném lỗi, nhưng tổng số dư tính từ các mục trả ra là 80 trong khi mọi trạng thái hợp lệ có tổng 100. Điều gì còn thiếu?

**Đáp án:** Thiếu bảo đảm **snapshot nhất quán xuyên suốt lượt duyệt**. An toàn từng bước và không ném exception không đủ cho một tổng toàn cục chính xác.

**Câu 18.** Vì sao số version đầu/cuối giống nhau vẫn chưa phải bằng chứng đủ để duyệt dữ liệu mutable không khóa là an toàn?

**Đáp án:** Còn cần giao thức công bố/visibility, bảo vệ vòng đời, đảm bảo không truy cập bộ nhớ đang bị sửa, xử lý wraparound/ABA và quy tắc tăng version. Một counter thường không tự cung cấp các bảo đảm ấy.

**Ghi nhớ:** **Bộ duyệt nhất quán yếu** ưu tiên việc tiếp tục duyệt khi dữ liệu thay đổi, nhưng **không hứa một ảnh chụp cố định**. **Bộ duyệt ảnh chụp** cố định một phiên bản giúp báo cáo/thuật toán có đầu vào nhất quán, đổi lại chi phí sao chép hoặc quản lý phiên bản. **Bộ duyệt phát hiện sửa đổi** giúp nhận biết sử dụng iterator không phù hợp, nhưng **không phải cơ chế đồng bộ an toàn luồng**. Hãy chọn theo **mức nhất quán cần thiết, tần suất đọc–ghi, kích thước dữ liệu, thời gian giữ khóa, bộ nhớ và kết quả nghiệp vụ**. Khi kết quả cần tính toán trên toàn cấu trúc như tổng tiền hoặc BFS, hãy gắn nó với **một phiên bản nhất quán**; khi hành động sau khi duyệt có thể thay đổi dữ liệu, hãy **kiểm tra lại điều kiện tại thời điểm cập nhật**.
