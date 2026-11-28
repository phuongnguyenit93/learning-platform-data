# Hạt giống ngẫu nhiên, khả năng tái hiện lỗi và dữ liệu bất lợi

Một cấu trúc dữ liệu ngẫu nhiên sử dụng các lựa chọn ngẫu nhiên để đạt hiệu năng tốt **trên kỳ vọng**, ngay cả khi thứ tự dữ liệu đầu vào không thuận lợi. Treap gán mức ưu tiên ngẫu nhiên cho nút; skip list tung đồng xu để chọn chiều cao của nút; bảng băm có thể chọn ngẫu nhiên một hàm băm trong một họ hàm. Cùng một tập khóa nhưng hai lần chạy có thể tạo ra hình dạng khác nhau và tốn thời gian khác nhau.

Điều này dẫn tới ba câu hỏi thực tế: làm thế nào kiểm thử lại một lỗi đã xuất hiện ngẫu nhiên, làm thế nào đánh giá cấu trúc trước dữ liệu bất lợi, và khi nào tính ngẫu nhiên thực sự bảo vệ được hiệu năng?

Sau bài này, người học có thể:

- Giải thích quan hệ giữa **seed (hạt giống)**, bộ sinh số giả ngẫu nhiên và các quyết định của cấu trúc dữ liệu.
- Tạo ca kiểm thử tái hiện được bằng cách ghi seed, chuỗi thao tác và các điều kiện chạy có liên quan.
- Phân biệt độ phức tạp kỳ vọng với giới hạn trường hợp xấu nhất, đồng thời nhận diện dữ liệu bất lợi và đối thủ có khả năng quan sát hoặc dự đoán tính ngẫu nhiên.

## 1. Seed điều khiển điều gì?

Phần lớn chương trình dùng **bộ sinh số giả ngẫu nhiên** (*pseudorandom number generator*, PRNG). Từ seed ban đầu `s`, PRNG tạo một chuỗi giá trị xác định:

\[
(r_1,r_2,r_3,\ldots)=\operatorname{PRNG}(s).
\]

Trong cùng cách cài đặt PRNG, cùng seed và cùng thứ tự gọi bộ sinh sẽ tạo cùng chuỗi số. Thuật toán lấy các số này để quyết định mức ưu tiên, chiều cao, vị trí chèn hay hàm băm. Vì vậy, **seed không tự quyết định toàn bộ kết quả**: chuỗi thao tác phải giống nhau, vì thao tác nào tiêu thụ thêm một lần sinh số cũng có thể làm mọi quyết định phía sau thay đổi.

Ví dụ, một treap dùng tính chất cây tìm kiếm nhị phân theo `key` và tính chất min-heap theo `priority`:

- Với mỗi nút, khóa ở cây con trái nhỏ hơn khóa của nút; khóa ở cây con phải lớn hơn.
- `priority` của nút cha không lớn hơn `priority` của các nút con.
- Mỗi nút mới được gán một `priority` giả ngẫu nhiên. Phép xoay bảo toàn thứ tự khóa và phục hồi tính chất heap.

Nếu priority được sinh độc lập từ cùng một phân phối gần như liên tục, chiều cao treap là \(O(\log n)\) **trên kỳ vọng**; tìm kiếm và cập nhật có chi phí kỳ vọng \(O(\log n)\). Một hình dạng đặc biệt vẫn có thể cao \(\Theta(n)\). Cụm từ “trên kỳ vọng” nói về phép lấy trung bình qua các lựa chọn ngẫu nhiên của thuật toán, không phải cam kết mọi lần chạy đều nhanh.

| Cấu trúc | Quyết định ngẫu nhiên | Chi phí thường được phân tích | Trường hợp xấu nhất |
| --- | --- | --- | --- |
| Treap | Priority độc lập cho mỗi khóa | Tìm/chèn/xóa \(O(\log n)\) kỳ vọng | \(O(n)\) nếu cây suy biến |
| Skip list | Mức của mỗi nút được chọn ngẫu nhiên | Tìm/chèn/xóa \(O(\log n)\) kỳ vọng khi xác suất thăng mức cố định | \(O(n)\) khi không có các đường tắt hữu ích |
| Bảng băm dùng họ hàm ngẫu nhiên | Chọn hàm băm hoặc khóa bí mật cho hàm băm | Tra cứu \(O(1)\) kỳ vọng với các giả thiết về phân phối băm, tải và xử lý va chạm | \(O(n)\) với phương án dây chuyền khi mọi khóa va chạm |

Các kết quả kỳ vọng đều dựa trên **giả thiết cụ thể** về cơ chế sinh ngẫu nhiên và mô hình đầu vào; chỉ gọi `random()` không đủ để chứng minh chúng.

## 2. Tái hiện cấu trúc bằng PRNG cục bộ

Đoạn mã Python 3.10+ dưới đây cài đặt phần **chèn khóa nguyên không trùng** của treap. Mỗi đối tượng giữ riêng một PRNG để những lời gọi ngẫu nhiên của phần mềm khác không làm thay đổi cấu trúc. Nếu khóa đã tồn tại, thao tác chèn không tiêu thụ thêm số ngẫu nhiên.

```python
import random
from dataclasses import dataclass


@dataclass
class Node:
    key: int
    priority: int
    left: "Node | None" = None
    right: "Node | None" = None


def rotate_right(root: Node) -> Node:
    pivot = root.left
    assert pivot is not None
    root.left = pivot.right
    pivot.right = root
    return pivot


def rotate_left(root: Node) -> Node:
    pivot = root.right
    assert pivot is not None
    root.right = pivot.left
    pivot.left = root
    return pivot


class Treap:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.root: Node | None = None

    def insert(self, key: int) -> None:
        self.root = self._insert(self.root, key)

    def _insert(self, node: Node | None, key: int) -> Node:
        if node is None:
            return Node(key, self.rng.getrandbits(128))

        if key < node.key:
            node.left = self._insert(node.left, key)
            if node.left.priority < node.priority:
                node = rotate_right(node)
        elif key > node.key:
            node.right = self._insert(node.right, key)
            if node.right.priority < node.priority:
                node = rotate_left(node)
        return node


def snapshot(node: Node | None):
    if node is None:
        return None
    return (node.key, node.priority,
            snapshot(node.left), snapshot(node.right))


operations = [8, 3, 10, 1, 6, 14, 4, 7]
a, b = Treap(seed=2026), Treap(seed=2026)
for key in operations:
    a.insert(key)
    b.insert(key)

assert snapshot(a.root) == snapshot(b.root)
print("Tái hiện cùng treap:", snapshot(a.root) == snapshot(b.root))
# Tái hiện cùng treap: True
```

`snapshot` lưu cả khóa, priority và cấu trúc cây nên phép so sánh mạnh hơn việc chỉ so sánh tập khóa. Ví dụ sử dụng `random.Random` để **kiểm thử và giảng dạy**; đây là bộ sinh có thể dự đoán, không phù hợp để giữ bí mật trước đối thủ. Priority 128 bit khiến va chạm hiếm trong ví dụ, nhưng không loại bỏ hoàn toàn khả năng hai priority bằng nhau. Một hệ thống thực tế cần quy định cách xử lý hòa và xem xét chi phí đệ quy khi cây suy biến.

Để có kết quả lặp lại, cần giữ ổn định cả phiên bản thuật toán, PRNG và thứ tự thao tác. Khi chuyển ngôn ngữ hoặc phiên bản runtime, không nên mặc định một seed sẽ tạo cùng các giá trị `getrandbits`; nếu cần tái hiện xuyên môi trường, hãy ghi lại **chính các quyết định ngẫu nhiên đã sử dụng** hoặc cố định rõ thuật toán PRNG và cách ánh xạ đầu ra.

## 3. Ghi đủ dữ liệu để tái hiện một lỗi

Giả sử một lần chạy kiểm thử phát hiện treap có nút con vi phạm tính chất heap. Thông báo “đôi khi lỗi sau vài trăm lần chèn” gần như không thể gỡ lỗi. Một hồ sơ tái hiện hữu ích nên có:

| Thông tin | Vì sao cần |
| --- | --- |
| Seed và thuật toán PRNG | Dựng lại chuỗi lựa chọn ngẫu nhiên |
| Chuỗi thao tác **có thứ tự**, bao gồm khóa và giá trị nếu có | Tái tạo trạng thái và số lần tiêu thụ ngẫu nhiên |
| Phiên bản mã nguồn và runtime | Loại trừ thay đổi về thuật toán, cách sinh số hoặc thứ tự duyệt |
| Cấu hình ảnh hưởng đến cấu trúc (xử lý trùng khóa, hệ số tải, độ cao tối đa, v.v.) | Dựng đúng các nhánh xử lý |
| Bất biến bị vi phạm, bước thao tác đầu tiên gây lỗi, kết quả mong đợi/thực tế | Xác định điều kiện thất bại cụ thể |
| Thông tin luồng/chạy song song nếu có | Vì cùng seed vẫn có thể cho lịch xen kẽ thao tác khác nhau |

Ví dụ về **bản ghi một ca lỗi giả định**:

```text
structure: treap
implementation: commit <ma-commit>
runtime: Python <phien-ban>
prng: random.Random; seed: 2026
operations:
  insert(8), insert(3), insert(10), insert(1), insert(6)
failure:
  sau insert(6), priority cua con nho hon priority cua cha
```

Quy trình gỡ lỗi: chạy lại seed và chuỗi thao tác; đặt kiểm tra bất biến sau mỗi bước; tìm thao tác đầu tiên gây sai; thu nhỏ ca thử bằng cách bỏ những thao tác không cần thiết. **Lưu ý khi thu nhỏ:** bỏ một thao tác có thể làm số lần rút ngẫu nhiên thay đổi và khiến lỗi biến mất. Khi cần, ghi lại dãy priority đã cấp phát hoặc cho phép bộ kiểm thử cấp trực tiếp từng quyết định ngẫu nhiên. Không kết luận rằng lỗi đã hết chỉ vì thử một seed khác không gặp lỗi.

Đối với chương trình đa luồng, seed cùng nhật ký đầu vào có thể vẫn chưa đủ. Lịch thực thi, thứ tự tranh chấp khóa và trạng thái chia sẻ cũng có thể phải được ghi hoặc kiểm soát để tái hiện chính xác.

## 4. Dữ liệu bất lợi và mô hình đối thủ

**Dữ liệu bất lợi** là đầu vào khiến một phương án xử lý chịu chi phí lớn hoặc bộc lộ lỗi: khóa tăng dần, trùng lặp dày đặc, nhiều khóa có cùng giá trị băm, hoặc chuỗi thao tác được chọn sau khi quan sát hành vi hệ thống. Cần phân biệt dữ liệu có hình dạng xấu với đối thủ **dự đoán được các lựa chọn ngẫu nhiên**.

### Một treap có thể thành danh sách liên kết

Xét bốn khóa `1, 2, 3, 4` với priority tương ứng `1, 2, 3, 4` (giá trị nhỏ ưu tiên hơn). Cả thứ tự khóa và priority cùng tăng, nên treap hợp lệ nhưng chỉ có nhánh phải:

```text
1 (p=1)
  \
   2 (p=2)
     \
      3 (p=3)
        \
         4 (p=4)
```

Chiều cao là \(\Theta(n)\), nên tìm `4` đi qua toàn bộ dãy. Tuy nhiên, với các priority **độc lập và có thứ tự phân biệt đều khả dĩ**, xác suất đúng thứ tự tăng nghiêm ngặt này cho `n` khóa cố định chỉ là \(1/n!\). **Khóa tăng dần tự nó không đủ để phá treap** nếu priority thực sự độc lập với khóa; đó là khác biệt căn bản so với cây BST thường chèn tuần tự không tự cân bằng.

Ngược lại, nếu người gửi dữ liệu biết trước dãy priority và có thể điều khiển thứ tự khóa ứng với từng lần rút số, họ có thể tìm một cách gán khóa làm treap lệch. Đây là lý do chứng minh kỳ vọng phải nêu rõ **đối thủ chọn đầu vào khi nào**:

| Mô hình | Tình huống | Cần thận trọng |
| --- | --- | --- |
| Đầu vào cố định trước các lựa chọn ngẫu nhiên (*oblivious*) | Danh sách khóa được quyết định trước; thuật toán rút priority độc lập sau đó | Thường phù hợp với các phân tích kỳ vọng tiêu chuẩn |
| Đầu vào thích ứng (*adaptive*) | Đối thủ quan sát thời gian, cấu trúc hoặc kết quả các lần trước rồi chọn khóa tiếp theo | Phải phân tích lại khả năng rò rỉ và mức độc lập cần thiết |
| Đối thủ biết seed/đoán được PRNG | Các lựa chọn tương lai có thể bị tính trước | Seed cố định công khai không cung cấp bảo vệ trước đầu vào chủ đích |

Ví dụ khác là **tấn công va chạm băm**: nếu nhiều khóa rơi vào cùng một bucket của bảng băm dùng chaining, một thao tác có thể tốn \(O(n)\). Việc chọn họ hàm băm ngẫu nhiên hoặc hàm băm có khóa bí mật có thể giảm khả năng đối thủ tạo va chạm chủ đích, nhưng hiệu quả phụ thuộc vào họ hàm, nguồn ngẫu nhiên, cách xử lý bucket và những gì đối thủ quan sát được. Một seed bí mật cũng không biến thời gian xử lý trường hợp xấu nhất thành bảo đảm \(O(1)\).

### Chọn biện pháp phù hợp

- **Bài học, kiểm thử, benchmark:** truyền seed cố định và PRNG cục bộ; ghi seed của ca thất bại để chạy lại.
- **Dịch vụ nhận khóa từ người dùng không tin cậy:** tránh để đối thủ biết hoặc suy ra toàn bộ trạng thái PRNG; cân nhắc nguồn ngẫu nhiên mật mã (*CSPRNG*) và hàm băm có khóa bí mật. Với Python, `random.Random` không cung cấp tính bí mật này.
- **Yêu cầu độ trễ xấu nhất chặt chẽ:** dùng cấu trúc có bảo đảm tất định phù hợp, như AVL/red-black tree với tìm/chèn/xóa \(O(\log n)\), hoặc có cơ chế phát hiện và chuyển sang phương án dự phòng khi độ sâu/chi phí vượt ngưỡng.

Nếu seed đóng vai trò bí mật bảo vệ dịch vụ, **không ghi seed thô vào log mà người dùng hay bên ngoài có thể đọc**. Việc tái hiện khi đó cần cơ chế lưu an toàn, quyền truy cập phù hợp hoặc ghi quyết định ngẫu nhiên trong môi trường kiểm thử được kiểm soát.

## 5. Kiểm thử đúng tính chất và hiệu năng

Kiểm thử một cấu trúc ngẫu nhiên cần tách hai loại câu hỏi:

**Tính đúng đắn:** Bất kể seed là gì, sau từng thao tác các bất biến vẫn phải đúng. Với treap: thứ tự BST, thứ tự priority theo heap, xử lý khóa trùng và tập khóa hiện có đều phải chính xác. Lỗi bất biến là lỗi chương trình, không thể được biện hộ bằng xác suất nhỏ.

**Hiệu năng:** Thử nhiều seed và nhiều phân phối đầu vào để quan sát chiều cao, số phép so sánh, số lần truy cập bộ nhớ và độ trễ. Đồ thị có thể lệch ở một seed hiếm; một ngưỡng quá cứng cho chiều cao sẽ gây kiểm thử thất bại ngẫu nhiên. Nếu cần xác nhận yêu cầu thống kê, phải xác định cỡ mẫu, phân phối và tiêu chuẩn chấp nhận phù hợp.

Một ma trận kiểm thử nhỏ nên gồm các nhóm sau:

| Nhóm đầu vào | Lỗi hoặc giả thiết muốn kiểm tra |
| --- | --- |
| Khóa tăng dần, giảm dần | Không vô tình phụ thuộc vào dữ liệu đã xáo trộn |
| Khóa ngẫu nhiên, tập rất nhỏ, tập lớn | Cạnh biên và xu hướng khi \(n\) tăng |
| Chèn khóa trùng, tìm khóa không tồn tại, xóa lặp (nếu hỗ trợ xóa) | Bất biến, ngữ nghĩa và số lượt rút PRNG |
| Khóa gây va chạm băm trong một cấu hình thử nghiệm | Đường xử lý bucket xung đột và chi phí khi va chạm |
| Nhiều seed khác nhau với **cùng** thao tác | Độ nhạy với lựa chọn ngẫu nhiên, tìm ca lỗi hiếm |
| Chuỗi thao tác chọn sau phản hồi trước đó | Đánh giá giả thiết trước đối thủ thích ứng |

Ví dụ, có thể mở rộng mã treap ở mục 2 bằng hàm kiểm tra mọi nút và chạy nhiều seed:

```python
def valid(node, low=None, high=None):
    if node is None:
        return True
    if low is not None and node.key <= low:
        return False
    if high is not None and node.key >= high:
        return False
    if node.left is not None and node.left.priority < node.priority:
        return False
    if node.right is not None and node.right.priority < node.priority:
        return False
    return (valid(node.left, low, node.key)
            and valid(node.right, node.key, high))


for seed in range(100):
    t = Treap(seed)
    for key in [8, 3, 10, 1, 6, 14, 4, 7, 6]:
        t.insert(key)
        assert valid(t.root), f"Lỗi với seed={seed}, key={key}"
```

Đoạn kiểm tra này phát hiện vi phạm BST/heap, nhưng không tự kiểm tra đầy đủ tập khóa hay hiệu năng; cần thêm phép đối chiếu với một cấu trúc tham chiếu như `set` và phép đo riêng khi triển khai thực tế. Cũng không nên coi 100 seed là bằng chứng chắc chắn không còn lỗi: một lỗi chỉ xuất hiện ở xác suất rất thấp có thể không bị kích hoạt.

**Nguyên tắc thực hành:** seed cố định giúp tái hiện; nhiều seed giúp mở rộng không gian thử nghiệm; đầu vào bất lợi giúp thử giới hạn của giả thiết; cấu trúc có bảo đảm tất định giúp đáp ứng yêu cầu trường hợp xấu nhất. Mỗi công cụ giải một phần khác nhau của bài toán.

## 6. Bài tập tự kiểm tra

1. **Cùng seed, khác cây:** Hai treap dùng cùng seed nhưng một chương trình chèn `5, 2, 8`, chương trình kia chèn `2, 5, 8`. Có thể kết luận snapshot giống nhau không? Giải thích.
2. **Đúng hay sai:** “Nếu đã ngẫu nhiên hóa priority thì dãy khóa tăng dần chắc chắn tạo treap có chiều cao \(O(\log n)\).”
3. **Thiết kế kiểm thử:** Một lỗi chỉ xuất hiện khi trùng khóa được chèn xen giữa các thao tác khác. Cần lưu gì để chạy lại lỗi và cần kiểm tra điều gì về số lượt rút PRNG?
4. **Chọn cấu trúc:** Một API công khai cần thời gian tra cứu có giới hạn xấu nhất dự đoán được, trong khi người dùng kiểm soát hoàn toàn khóa. Chỉ dùng seed cố định có đáp ứng yêu cầu không?

**Gợi ý đáp án:** (1) Không nhất thiết: priority được cấp theo thứ tự chèn, nên mỗi khóa có thể nhận priority khác nhau. (2) Sai: \(O(\log n)\) ở đây là kết quả kỳ vọng; vẫn tồn tại cây cao tuyến tính. (3) Lưu seed, PRNG, phiên bản, chuỗi thao tác đầy đủ và bước đầu tiên sai; xác nhận chèn trùng có hoặc không tiêu thụ số ngẫu nhiên theo đúng đặc tả. (4) Không; cần cấu trúc có giới hạn xấu nhất thích hợp hoặc cơ chế dự phòng được phân tích rõ.
