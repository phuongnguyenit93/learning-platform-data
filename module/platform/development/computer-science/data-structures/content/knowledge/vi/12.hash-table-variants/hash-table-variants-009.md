# Băm nhất quán khi phân chia khóa giữa các nút lưu trữ

Khi dữ liệu lớn hơn khả năng của một máy, hệ thống thường phân chia các cặp **khóa–giá trị** cho nhiều nút lưu trữ (*storage nodes*). Câu hỏi không chỉ là tìm khóa nhanh, mà còn là: **khóa này thuộc máy nào, và khi thêm hoặc mất một máy thì cần di chuyển bao nhiêu dữ liệu?**

**Băm nhất quán** (*consistent hashing*) giải quyết bài toán phân phối khóa lên những nút có thể tham gia hoặc rời cụm. Tư tưởng cốt lõi là đặt cả **khóa** và **nút** trên cùng một **vòng không gian băm** (*hash ring*). Mỗi khóa được gán cho nút đầu tiên theo chiều kim đồng hồ, thay vì lấy giá trị băm theo số lượng nút hiện có.

Đây là bài học trong chương **Biến thể bảng băm** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu bất biến ánh xạ, thao tác thêm/xóa nút, chi phí tra cứu và tái phân phối, cách sử dụng nút ảo (*virtual nodes*), và đánh đổi về tải, tính sẵn sàng, bộ nhớ để lựa chọn giải pháp cho hệ thống phân tán.

## 1. Vì sao phép chia dư theo số máy gây di chuyển dữ liệu?

Một cách phân chia đơn giản là:

\[
\operatorname{node}(k)=h(k)\bmod N,
\]

trong đó \(N\) là số máy và các máy được đánh số từ 0 đến \(N-1\). Công thức dễ tính nhưng **phụ thuộc trực tiếp vào \(N\)**.

Giả sử bốn khóa có giá trị băm lần lượt là 10, 11, 12, 13:

| Khóa có giá trị băm | Khi có 3 nút: \(h(k)\bmod3\) | Khi có 4 nút: \(h(k)\bmod4\) |
| ---: | ---: | ---: |
| 10 | 1 | 2 |
| 11 | 2 | 3 |
| 12 | 0 | 0 |
| 13 | 1 | 1 |

Chỉ thêm một nút, trong ví dụ đã có **hai trên bốn khóa** đổi nơi lưu. Với giá trị băm phân bố đều và các tập nút được đánh số theo cách đơn giản này, khi đổi từ \(N\) sang \(N+1\), **phần lớn khóa thường phải ánh xạ lại** (nhất là khi \(N\) lớn), tạo ra nhiều lần sao chép dữ liệu và có thể gây nghẽn mạng.

Băm nhất quán hướng tới hai đặc điểm:

1. **Ít di chuyển khóa (*minimal disruption*):** chỉ một phần tương đối nhỏ của không gian khóa đổi chủ sở hữu khi thay đổi thành viên cụm.
2. **Định tuyến xác định (*deterministic mapping*):** với cùng hàm băm và cùng cấu hình nút, mọi phía tính ra cùng nút chứa khóa.

Từ **“nhất quán”** ở đây trước hết nói về **tính ổn định của phép phân phối khóa khi thay đổi tập nút**, **không phải** cam kết giao dịch nhất quán mạnh (*strong consistency*) của dữ liệu.

## 2. Vòng băm và quy tắc tìm nút kế tiếp

Giả sử dùng không gian giá trị băm gồm \(2^b\) địa chỉ:

\[
\mathcal{H}=\{0,1,\ldots,2^b-1\}.
\]

Ta có thể hình dung các địa chỉ nằm trên **một vòng tròn**: sau giá trị lớn nhất, vòng quay về 0. Mỗi nút lưu trữ được ánh xạ đến một hoặc nhiều vị trí trên vòng. Mỗi khóa cũng được băm đến một vị trí.

**Quy tắc chuẩn trong bài:** Từ vị trí băm của khóa, đi **theo chiều kim đồng hồ**, chọn **nút đầu tiên có vị trí lớn hơn hoặc bằng vị trí khóa**. Nếu đi hết vòng mà chưa gặp nút, chọn nút ở vị trí nhỏ nhất.

Viết dưới dạng:

\[
\boxed{\operatorname{owner}(k)
=\operatorname{successor}\bigl(h(k)\bigr).}
\]

Trong đó hàm **successor** trả về nút đầu tiên theo thứ tự vòng băm, kể cả nút ở **chính** vị trí băm của khóa.

~~~text
Không gian băm minh họa: 0...99, nối đuôi 99 với 0.

            A@10            B@40            C@80
      ───────●────────────────●────────────────●───────
      0                                                  99
      ^__________________________________________________|
                       Quay vòng về 0

  h(k)= 7  → A@10
  h(k)=27  → B@40
  h(k)=53  → C@80
  h(k)=91  → A@10  (vòng về đầu)
~~~

Với ba nút A, B, C như trên, mỗi nút chịu trách nhiệm đoạn khóa **từ ngay sau nút trước đó đến chính vị trí của mình**:

| Nút chủ | Khoảng giá trị băm thuộc sở hữu |
| --- | --- |
| A@10 | \((80,99]\cup[0,10]\) |
| B@40 | \((10,40]\) |
| C@80 | \((40,80]\) |

Các khoảng trên dùng không gian rời rạc 0–99; dấu ngoặc được chọn theo quy tắc **successor lớn hơn hoặc bằng**. Mỗi giá trị băm có **đúng một nút chủ** nếu vị trí của các nút phân biệt, và mọi giá trị đều được bao phủ.

### Bất biến định tuyến

Với tập nút đang hoạt động \(V\):

- Mỗi token của nút có một vị trí xác định trên vòng.
- Mỗi khóa \(k\) được gán cho **nút đầu tiên trên vòng tại hoặc sau \(h(k)\)**.
- Nếu nút có nhiều vị trí ảo, sau khi tìm token đầu tiên, phải quy về **nút vật lý** đứng sau token đó.
- Mọi máy khách định tuyến phải dùng **cùng cách băm, cùng thông tin thành viên cụm và cùng quy tắc xử lý trường hợp bằng nhau**.

Không nhất thiết mọi nút đều được chia đúng số khóa bằng nhau: kích thước cung trên vòng và phân bố khóa sẽ quyết định tỷ lệ thực tế.

## 3. Thêm nút: chỉ một đoạn khóa đổi chủ

Tiếp tục vòng băm có A@10, B@40, C@80. Giả sử thêm **D@60**, nằm giữa B và C:

~~~text
Trước: A@10 ─── B@40 ─────────────── C@80 ─── (vòng lại A)
Sau:   A@10 ─── B@40 ── D@60 ─────── C@80 ─── (vòng lại A)

   Trước khi có D:   (40,80] thuộc C
   Sau khi có D:     (40,60] thuộc D; (60,80] vẫn thuộc C
~~~

| Giá trị băm của khóa | Trước khi thêm D | Sau khi thêm D | Có di chuyển? |
| ---: | --- | --- | --- |
| 27 | B | B | Không |
| 40 | B | B | Không |
| 53 | C | **D** | **Có** |
| 60 | C | **D** | **Có** |
| 65 | C | C | Không |
| 91 | A | A | Không |

Chỉ các khóa có vị trí trong đoạn **\((40,60]\)** được chuyển từ C sang D. Các đoạn khác giữ nguyên chủ sở hữu.

**Tại sao điều này hữu ích?** Thay vì phải phân phối lại hầu hết dữ liệu do đổi số máy như trong phép chia dư, hệ thống chỉ cần chuyển **những khóa thuộc đoạn vòng mà nút mới nhận**.

Nếu có \(N\) nút đang nằm ở các vị trí **độc lập và phân bố đều ngẫu nhiên** trên vòng, rồi thêm một nút có vị trí ngẫu nhiên tương tự, kỳ vọng tỷ lệ không gian băm mà nút mới nhận là:

\[
\boxed{\mathbb{E}[\text{tỷ lệ khóa đổi nút chủ}]\approx\frac{1}{N+1}.}
\]

Cách diễn giải “tỷ lệ khóa” cần thêm giả thiết rằng **vị trí băm của khóa phân bố đều**, độc lập với vị trí các nút, và các nút có trọng số ngang nhau. Đây là kết quả **kỳ vọng**, không phải cam kết mỗi lần thêm nút sẽ di chuyển đúng \(1/(N+1)\) dữ liệu. Với rất ít vị trí nút, một lần thêm có thể nhận đoạn rất lớn hoặc rất nhỏ.

## 4. Xóa hoặc mất nút: các khóa đi về nút kế tiếp

Khi một nút bị loại khỏi vòng, các khóa mà nó từng sở hữu được gán cho **nút kế tiếp theo chiều kim đồng hồ** trong cấu hình mới.

Ví dụ sau khi đã thêm D@60, ta có A@10, B@40, D@60, C@80. Nếu xóa B@40:

~~~text
Trước: A@10 ── B@40 ── D@60 ── C@80
Sau:   A@10 ─────────── D@60 ── C@80

   Đoạn (10,40] vốn thuộc B → chuyển cho D.
~~~

Các khóa của A, C và phần vốn đã thuộc D không tự động đổi chủ. Nếu việc xóa là **thu hồi nút có kế hoạch**, có thể chuyển dữ liệu trước khi cho nút rời cụm. Nếu nút **hỏng đột ngột**, không được nhầm việc **tính được chủ mới** với việc **dữ liệu đã tồn tại sẵn ở chủ mới**. Cần cơ chế sao chép dự phòng, phục hồi hoặc kho dữ liệu nguồn; nếu không, dữ liệu chỉ lưu trên nút hỏng vẫn có thể mất.

Một lưu ý khác: hệ thống phải đồng bộ **thông tin thành viên cụm**. Nếu hai máy khách nhìn thấy hai vòng khác nhau, chúng có thể cùng đọc hoặc ghi một khóa ở **hai nút khác nhau**. Băm nhất quán tự nó không cung cấp cơ chế phát hiện hỏng, truyền trạng thái hay đảm bảo đồng thuận.

## 5. Tra cứu hiệu quả: sắp thứ tự token và tìm kiếm nhị phân

Trong hiện thực thực tế, không cần duyệt tất cả token trên vòng từng lần tra cứu. Hãy lưu các token ở một **mảng có thứ tự tăng dần**:

~~~text
positions = [10, 40, 60, 80]
nodes     = [ A,  B,  D,  C]

Key hash = 53:
  lower_bound(positions, 53) = index 2
  → token 60 → node D

Key hash = 91:
  lower_bound(positions, 91) = hết mảng
  → quay về index 0 → node A
~~~

**lower_bound** trả về vị trí đầu tiên có token **lớn hơn hoặc bằng** giá trị băm khóa. Với \(V\) token đã sắp xếp, tìm kiếm nhị phân tốn:

\[
\boxed{T_{\mathrm{route}}=O(\log V).}
\]

Nếu \(V\) rất nhỏ, quét tuyến tính \(O(V)\) cũng có thể đủ đơn giản. Một cây tìm kiếm có thứ tự hoặc các cấu trúc chỉ mục khác có thể giúp cập nhật token mà không cần dịch phần tử trong mảng.

**Các thao tác khác nhau cần tách bạch:**

1. **Định tuyến:** tìm nút phải phục vụ khóa từ metadata của vòng.
2. **Tra cứu cục bộ:** nút đã chọn dùng bảng băm, cây hoặc hệ lưu trữ khác để lấy bản ghi.
3. **Truyền dữ liệu qua mạng:** một yêu cầu đọc/ghi còn chịu độ trễ mạng, I/O đĩa, đồng bộ và lỗi nút.

Do đó \(O(\log V)\) là chi phí **tra vị trí token**, không phải thời gian toàn bộ hệ thống trả về giá trị.

## 6. Nút ảo giúp giảm lệch tải

Nếu mỗi nút vật lý chỉ được gán **một token**, các cung vòng tạo ra bởi những vị trí ngẫu nhiên thường có độ dài **không đều**. Nút sở hữu cung dài nhận nhiều khóa hơn nút có cung ngắn, ngay cả khi tất cả các khóa phân bố đều.

**Nút ảo** (*virtual node* hay *vnode*) là cách gán **nhiều token khác nhau** cho cùng một nút vật lý. Ví dụ, với một nút có định danh **A**, sinh token từ những chuỗi như:

~~~text
hash("node:A:0")
hash("node:A:1")
hash("node:A:2")
...
hash("node:A:63")
~~~

Mỗi token hoạt động như một vị trí riêng trên vòng, nhưng **mọi vị trí đó đều quy về nút vật lý A**. Một nút mới tham gia sẽ nhận những **đoạn nhỏ tại nhiều vị trí** thay vì chỉ một đoạn duy nhất.

**Ví dụ minh họa phân bố token:**

~~~text
Vòng đã sắp theo chiều kim đồng hồ:
  A1 → C1 → B1 → A2 → B2 → C2 → B3 → A3 → C3 → (về A1)

Nút vật lý A có 3 vnode: A1, A2, A3.
Nút vật lý B có 3 vnode: B1, B2, B3.
Nút vật lý C có 3 vnode: C1, C2, C3.
~~~

### Ưu điểm

- **Cân bằng tải tốt hơn theo thống kê:** nhiều đoạn nhỏ cộng lại có xu hướng giảm độ chênh lệch tổng phần không gian băm mỗi nút sở hữu.
- **Di chuyển dữ liệu rải đều:** khi thêm/xóa nút, các đoạn liên quan có thể nằm rải rác trên vòng, giúp phân tán công việc chuyển dữ liệu giữa nhiều máy.
- **Hỗ trợ nút khác năng lực:** máy có dung lượng/hiệu năng lớn hơn có thể được cấp nhiều vnode hơn.

### Đánh đổi

- Số token \(V\) tăng, kéo theo chi phí metadata, khởi tạo, định tuyến và quản lý chuyển dữ liệu.
- Mỗi vnode không phải một bản sao dữ liệu độc lập; **vnode chỉ là vị trí ánh xạ**.
- Nếu chọn rất ít vnode, tải có thể lệch nhiều. Nếu chọn quá nhiều, việc theo dõi và chuyển giao hàng loạt dải khóa trở nên phức tạp.
- Số vnode tỷ lệ với năng lực chỉ là **phép xấp xỉ trọng số**. Số lượng khóa, kích thước bản ghi, mức truy cập và tải CPU có thể khác nhau rất nhiều.

Với \(N\) nút ngang năng lực và mỗi nút có cùng \(v\) token được phân bố đủ ngẫu nhiên, tổng token là \(V=Nv\). Càng nhiều token độc lập, tỷ lệ không gian băm mỗi nút nhận thường ổn định hơn quanh \(1/N\), nhưng không có lời hứa **chính xác** \(1/N\) cho mỗi nút.

## 7. Sao chép dự phòng: nhiều nút sở hữu một khóa

Trong hệ thống phân tán, đặt khóa ở **một nút** có thể tạo điểm lỗi duy nhất. Một chính sách phổ biến là chọn **\(R\) nút vật lý phân biệt** làm các nơi lưu bản sao (*replicas*):

1. Định tuyến đến token đầu tiên từ vị trí băm của khóa: chọn nút vật lý đứng sau token đó.
2. Tiếp tục đi theo vòng để lấy các nút vật lý khác.
3. **Bỏ qua vnode của nút đã chọn** để tránh lưu hai bản sao trên cùng một máy.
4. Dừng khi đã chọn đủ \(R\) nút khác nhau, hoặc hết số nút vật lý đang có.

~~~text
Vòng vnode:  A1 → B1 → A2 → C1 → B2 → C2 → (về A1)
Key hash nằm trước A1; yêu cầu 3 bản sao:

   A1 → nút A: bản sao 1
   B1 → nút B: bản sao 2
   A2 → nút A: bỏ qua vì A đã được chọn
   C1 → nút C: bản sao 3

Replica set = [A, B, C]
~~~

Nếu có \(N\) nút vật lý, số bản sao **phân biệt về mặt nút** không thể vượt \(N\). Một số hệ thống còn cần phân bố theo **rack, vùng sẵn sàng hoặc trung tâm dữ liệu** để tránh tất cả bản sao cùng chịu một sự cố. Chỉ lấy \(R\) nút kế tiếp không tự bảo đảm phân tán theo miền lỗi.

**Cần tách bạch ba khái niệm:**

| Khái niệm | Băm nhất quán cung cấp gì? | Điều gì vẫn phải thiết kế thêm? |
| --- | --- | --- |
| Vị trí lưu | Xác định nút chủ và các ứng viên replica theo vòng | Tạo bản sao thực sự, sao chép khi thay đổi thành viên |
| Chịu lỗi | Có thể tìm nút thay thế nếu một nút rời vòng | Dữ liệu đã được sao chép, phát hiện lỗi, phục hồi và chuyển tiếp truy vấn |
| Tính nhất quán đọc–ghi | Không quyết định trạng thái dữ liệu mới nhất | Đồng thuận, phiên bản, quorum, giải quyết xung đột hoặc giao thức phù hợp |

Khi thêm nút, **tập các replica** của một số khóa có thể thay đổi ngay cả khi nút chủ chưa đổi. Vì vậy, tỷ lệ **bản sao phải sao chép lại** không nhất thiết bằng tỷ lệ **khóa đổi nút chủ** trong công thức \(1/(N+1)\).

## 8. Mã Python: vòng băm có vnode và bản sao

Ví dụ sau tạo một **bộ định tuyến** bằng băm nhất quán, không phải một cụm lưu trữ phân tán hoàn chỉnh. Nó minh họa:

- Băm **ổn định qua các lần chạy** bằng SHA-256 thay vì hàm **hash** mặc định của Python (vì hàm đó có thể được ngẫu nhiên hóa giữa các tiến trình).
- Tạo cùng số vnode cho mỗi nút vật lý bằng định danh token ổn định.
- Tra cứu bằng **bisect** (*binary search*) trong danh sách token đã sắp xếp.
- Chọn \(R\) nút vật lý **không trùng nhau** cho bản sao.
- So sánh ánh xạ khóa **trước và sau** khi thêm hoặc xóa một nút.

~~~python
from bisect import bisect_left, insort
from hashlib import sha256


class ConsistentHashRing:
    def __init__(self, virtual_nodes=64):
        if type(virtual_nodes) is not int or virtual_nodes < 1:
            raise ValueError("virtual_nodes phải là số nguyên dương")

        self.virtual_nodes = virtual_nodes
        self.nodes = set()
        # Mỗi điểm: (vị trí băm, định danh nút vật lý, số thứ tự vnode).
        # Tuple tạo thứ tự xác định cả trong tình huống token trùng nhau.
        self.points = []

    @staticmethod
    def _digest(data: bytes) -> int:
        return int.from_bytes(sha256(data).digest(), "big")

    @staticmethod
    def _check_name(value):
        if not isinstance(value, str) or not value:
            raise ValueError("Nút và khóa phải là chuỗi không rỗng")

    def _node_token(self, node, vnode):
        # Tách miền băm của token nút với miền băm của khóa.
        name = node.encode("utf-8")
        payload = (
            b"node|" + len(name).to_bytes(4, "big")
            + name + b"|" + str(vnode).encode("ascii")
        )
        return self._digest(payload)

    def _key_token(self, key):
        name = key.encode("utf-8")
        return self._digest(b"key|" + len(name).to_bytes(4, "big") + name)

    def add_node(self, node):
        self._check_name(node)
        if node in self.nodes:
            return False
        self.nodes.add(node)

        for vnode in range(self.virtual_nodes):
            position = self._node_token(node, vnode)
            insort(self.points, (position, node, vnode))
        return True

    def remove_node(self, node):
        self._check_name(node)
        if node not in self.nodes:
            return False
        self.nodes.remove(node)
        self.points = [point for point in self.points if point[1] != node]
        return True

    def replicas(self, key, count=1):
        self._check_name(key)
        if type(count) is not int or count < 1:
            raise ValueError("count phải là số nguyên dương")
        if not self.points:
            raise LookupError("Vòng chưa có nút nào")

        position = self._key_token(key)
        # Trường thứ hai là chuỗi rỗng: tìm token đầu tiên
        # có vị trí >= position, cả khi có token trùng vị trí.
        start = bisect_left(self.points, (position, "", -1))
        start %= len(self.points)  # Quay vòng nếu vượt điểm lớn nhất.

        needed = min(count, len(self.nodes))
        chosen = []
        seen = set()
        for step in range(len(self.points)):
            _, node, _ = self.points[(start + step) % len(self.points)]
            if node not in seen:
                seen.add(node)
                chosen.append(node)
                if len(chosen) == needed:
                    break
        return chosen

    def owner(self, key):
        return self.replicas(key, 1)[0]


ring = ConsistentHashRing(virtual_nodes=64)
for node in ("A", "B", "C"):
    ring.add_node(node)

keys = [f"object:{i}" for i in range(10000)]
before = {key: ring.owner(key) for key in keys}

ring.add_node("D")
after_add = {key: ring.owner(key) for key in keys}
moved = [key for key in keys if before[key] != after_add[key]]

print("Số khóa đổi nút chủ:", len(moved))
print("Tỷ lệ:", f"{len(moved) / len(keys):.2%}")
print("Các bản sao cho object:42:", ring.replicas("object:42", 3))

# Khi chỉ thêm nút D và giữ nguyên các token cũ,
# khóa nào đổi chủ sở hữu đều chuyển đến D.
assert all(after_add[key] == "D" for key in moved)

ring.remove_node("D")
after_remove = {key: ring.owner(key) for key in keys}
assert after_remove == before
~~~

**Ý nghĩa của ví dụ:** kết quả ánh xạ phụ thuộc **định danh nút, số vnode, hàm băm và tập thành viên**, nhưng không phụ thuộc việc thêm nút trước hay sau trong vòng lặp tạo các nút cũ. Mã sử dụng cùng định danh và số vnode cho A, B, C nên khi loại D, vòng trở về đúng cấu hình ban đầu.

**Giới hạn quan trọng:**

1. Chương trình chỉ **tính nút đích**; nó **không gửi dữ liệu**, không đọc/ghi qua mạng và không xác minh bản sao đã tồn tại.
2. Danh sách Python dùng **insort**, khiến việc thêm một token có thể dịch \(O(V)\) phần tử. Với \(v\) vnode thêm mới, thao tác tạo token trên mảng có thể tốn tới \(O(vV+v^2)\), dù mỗi lần định vị bằng tìm kiếm nhị phân là \(O(\log V)\).
3. **remove_node** lọc lại danh sách token trong \(O(V)\); các cấu trúc cây cân bằng hoặc chỉ mục khác có thể thích hợp hơn nếu nút thay đổi thường xuyên.
4. Việc trùng giá trị SHA-256 rất khó xảy ra trong thực tế, nhưng tuple được sắp theo **vị trí, tên nút, số vnode** để có kết quả xác định nếu trùng. Triển khai sản xuất còn cần thống nhất rõ quy tắc tie-break, phiên bản hàm băm và mã hóa định danh.
5. Với nhiều vnode của cùng một nút, thuật toán chọn replica có thể phải **bỏ qua** nhiều token đã gặp. Trường hợp xấu nhất phải duyệt tới \(V\) token để chọn đủ các nút vật lý.
6. **Tỷ lệ dịch chuyển in ra chỉ là một phép đo trên bộ khóa ví dụ:** người học có thể chạy mã và thay đổi tập khóa, số vnode, tập nút để quan sát độ lệch so với kỳ vọng; không nên coi tỷ lệ đó là một hằng số bắt buộc.

### Một cách tự kiểm tra bằng tay trước khi chạy mã

Trong ví dụ vòng nhỏ ở mục 3, các giá trị băm được cho sẵn (10, 40, 60, 80), nên có thể xác minh toán học rằng thêm D@60 **chỉ đổi chủ các khóa có vị trí trong đoạn \((40,60]\)**. Khi băm SHA-256 trong mã trên, vị trí thực tế hoàn toàn khác ví dụ thủ công; mục đích của mã là quan sát **tính chất ít di chuyển**, không tạo lại chính xác các vị trí 10, 40, 60, 80.

## 9. Quy trình tái phân phối dữ liệu khi thay đổi thành viên

Việc đổi ánh xạ trong bảng định tuyến chỉ là **bước quyết định quyền sở hữu**; dữ liệu vật lý chưa tự di chuyển. Một quy trình thêm nút có thể gồm:

1. **Cập nhật kế hoạch thành viên:** xác định định danh, số vnode hoặc trọng số của nút mới; xuất phiên bản cấu hình vòng băm.
2. **Tính các dải khóa thay đổi:** so sánh token cũ và mới để biết những đoạn nào được chuyển từ nút cũ sang nút mới.
3. **Sao chép dữ liệu:** chuyển các bản ghi thuộc những dải mới, có thể giới hạn băng thông để tránh gây nghẽn hệ thống.
4. **Bắt kịp ghi mới:** áp dụng những thay đổi xảy ra **trong lúc đang sao chép** bằng nhật ký, chuyển tiếp ghi hoặc cơ chế đồng bộ phù hợp.
5. **Chuyển tuyến:** chỉ đánh dấu nút mới là nơi phục vụ chính sau khi điều kiện sẵn sàng và tính đúng đắn dữ liệu được đáp ứng.
6. **Dọn bản sao cũ:** xóa dữ liệu không còn thuộc trách nhiệm sau thời gian chuyển tiếp và sau khi xác minh không cần phục vụ truy vấn cũ.

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi tập nút"] --> B["Xây phiên bản vòng băm mới"]
    B --> C["Tính các dải khóa đổi chủ"]
    C --> D["Sao chép dữ liệu và bắt kịp cập nhật"]
    D --> E{"Dữ liệu đích đã sẵn sàng?"}
    E -->|Chưa| D
    E -->|Rồi| F["Chuyển định tuyến sang phiên bản mới"]
    F --> G["Dọn các bản sao không còn cần thiết"]
~~~

**Rời cụm có kế hoạch** có thể dùng quy trình tương tự theo chiều ngược lại. **Sự cố đột ngột** thì cần phục hồi từ bản sao khác hoặc hệ thống lưu trữ bền vững.

### Tại sao cần phiên bản cấu hình?

Giả sử máy khách X đã cập nhật vòng có D@60, còn máy khách Y vẫn dùng vòng A@10, B@40, C@80. Với khóa băm thành 53:

- X ghi vào **D**.
- Y vẫn ghi vào **C**.

Nếu không có giao thức kiểm soát trạng thái, hai nút có thể chứa **hai phiên bản khác nhau của cùng một khóa**. Các cơ chế như kiểm tra phiên bản, chuyển tiếp yêu cầu, dual-write trong giai đoạn chuyển tiếp, đồng bộ replica và quy tắc giải quyết xung đột cần được thiết kế rõ ràng.

Không thể chỉ yêu cầu mọi máy “dùng cùng hàm băm” rồi coi quá trình đổi thành viên là an toàn. Điều tối thiểu là cần thống nhất **phiên bản danh sách nút, cách tính token, trạng thái chuyển giao và quy tắc phục vụ đọc/ghi**.

## 10. Tải cân bằng trên vòng không bằng tải xử lý cân bằng

Băm nhất quán có xu hướng phân phối **không gian khóa** theo tỷ lệ số token hoặc trọng số. Tuy nhiên, hiệu năng cụm còn phụ thuộc:

- **Số lượng khóa** trên từng đoạn vòng.
- **Dung lượng từng khóa**, vì một khóa có thể chiếm nhiều gigabyte trong khi khóa khác chỉ vài byte.
- **Tần suất truy cập**, vì một khóa “nóng” có thể tạo phần lớn yêu cầu đọc/ghi.
- **Năng lực nút**, gồm CPU, RAM, ổ đĩa và băng thông mạng.
- **Chi phí replica**, vì một thao tác ghi có thể phải đến nhiều nút và đặt bản sao trên nhiều miền lỗi.

### Ví dụ về hotspot

Giả sử hai nút mỗi nút lưu khoảng 50% **số khóa**, nhưng một khóa thuộc nút A nhận 80% tổng lượng truy cập. Dù phân chia số khóa rất cân đối, nút A vẫn có thể quá tải.

**Virtual nodes không tự chia một khóa nóng thành nhiều phần.** Các cách xử lý phải xét ở tầng hệ thống như cache, bản sao phục vụ đọc, chia nhỏ một khóa thành nhiều khóa con hoặc phân tách quyền sở hữu theo mục đích ứng dụng.

### Nút có sức chứa khác nhau

Khi nút A có năng lực gấp đôi B, có thể cấp xấp xỉ **hai lần số vnode** cho A. Ví dụ nếu B có 64 vnode, A có thể có 128. Đây là **cách biểu diễn trọng số tương đối**, không đảm bảo A nhận chính xác hai lần lượng dữ liệu hay yêu cầu thực tế.

Thay đổi số vnode của một nút cũng là **thay đổi vòng băm**: sẽ có khóa đổi vị trí và cần chuyển giao dữ liệu. Đừng coi cập nhật trọng số là miễn phí.

## 11. Độ phức tạp và bộ nhớ

Đặt:

- \(N\): số nút vật lý.
- \(v\): số vnode trung bình trên mỗi nút.
- \(V\): tổng số token trên vòng, thông thường \(V\approx Nv\).
- \(K\): tổng số khóa dữ liệu.
- \(R\): số bản sao vật lý yêu cầu cho mỗi khóa.

| Thao tác hoặc tài nguyên | Chi phí thuật toán | Phạm vi |
| --- | --- | --- |
| Tính hash khóa | Phụ thuộc kích thước khóa, thường xem là \(O(1)\) khi độ dài có chặn | Không được bỏ qua chi phí băm chuỗi dài |
| Tra nút chủ trên mảng token có thứ tự | \(O(\log V)\) | Tìm token đầu tiên không nhỏ hơn vị trí khóa |
| Tìm \(R\) nút vật lý khác nhau | \(O(\log V + t)\) với \(t\) là số token phải duyệt | Trường hợp xấu nhất \(t=O(V)\); nếu cần ít replica và phân bố tốt, thường nhỏ hơn |
| Lưu metadata vòng | \(O(V)\) token và định danh nút | Chưa tính dữ liệu khóa–giá trị thực |
| Thêm một token vào mảng đã sắp | \(O(V)\) do dịch phần tử | Với cây có thứ tự, thao tác cập nhật chỉ mục có thể \(O(\log V)\) |
| Thêm nút với \(v\) vnode | Tùy cấu trúc chỉ mục; với mảng như ví dụ có thể \(O(vV+v^2)\) | Chỉ là xử lý **metadata**, chưa bao gồm sao chép khóa |
| Số khóa đổi nút chủ khi thêm nút ngang năng lực | Khoảng \(K/(N+1)\) **theo kỳ vọng** trong mô hình băm đều | Không phải bảo đảm cho một lần thay đổi cụ thể |
| Sao chép dữ liệu khi tái cân bằng | Tỷ lệ với số **byte** dữ liệu thực phải chuyển | Phụ thuộc kích thước bản ghi, mạng, I/O và replica |

**Một sự nhầm lẫn thường gặp:** Định tuyến một khóa trong \(O(\log V)\) không đồng nghĩa **thêm một nút** hoàn thành trong \(O(\log V)\). Chỉ mục token có thể cập nhật nhanh, nhưng việc chuyển dữ liệu tới nút mới có thể mất nhiều I/O và băng thông mạng.

### So sánh bộ nhớ định tuyến với bộ nhớ dữ liệu

Với 20 nút và trung bình 64 vnode mỗi nút, chỉ mục vòng có:

\[
V=20\cdot64=1\,280\text{ token}.
\]

Metadata này có thể được lưu trên các máy khách hoặc bộ định tuyến, trong khi dữ liệu của \(K\) khóa nằm ở những nút lưu trữ. **Độ lớn metadata tỷ lệ với số token chứ không nhất thiết với số khóa**. Nếu tăng số vnode lên rất nhiều để giảm lệch tải, chi phí metadata và quản lý dải khóa cũng tăng.

## 12. Các lựa chọn khác để phân chia khóa

Không phải mọi hệ thống phân tán đều cần một vòng băm cổ điển. Việc lựa chọn phụ thuộc cách thay đổi nút, yêu cầu cân bằng tải, khả năng phân bố bản sao và chi phí metadata.

| Cách phân chia | Cách xác định nơi lưu | Khi số nút thay đổi | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| **Modulo \(h(k)\bmod N\)** | Dùng phép chia dư theo số lượng nút | Thường làm nhiều khóa đổi địa chỉ | Rất đơn giản, phù hợp khi tập nút hầu như cố định |
| **Consistent hashing trên vòng** | Chọn token đầu tiên theo chiều kim đồng hồ | Chủ yếu chỉ thay đổi những đoạn vòng lân cận token được thêm/xóa | Cần quản lý token, vnode, cấu hình thành viên và chuyển giao dữ liệu |
| **Rendezvous hashing** (*highest-random-weight*) | Băm cặp *(khóa, nút)* và chọn nút có điểm cao nhất | Khi thêm nút, chỉ khóa mà nút mới thắng mới đổi chủ; khi xóa, chỉ khóa của nút bị xóa chuyển đi | Mô hình cơ bản tính điểm cho mọi nút, nên một lần tra có chi phí \(O(N)\) |
| **Jump consistent hash** | Tính chỉ số bucket bằng thuật toán nhảy dựa trên khóa và số bucket | Thêm bucket cuối có tính chất ít thay đổi ánh xạ | Hợp nhất cho các bucket đánh số liên tục; xử lý xóa tùy ý và nút vật lý không đồng nhất cần thiết kế thêm |
| **Phân đoạn cố định (*fixed sharding*)** | Chia khóa thành các shard có định danh độc lập rồi gán shard cho nút | Di chuyển **shard** giữa các nút | Cần metadata ánh xạ shard→nút nhưng điều khiển di chuyển trực tiếp hơn |

**Rendezvous hashing** cũng có tính ổn định khi tập nút thay đổi, nhưng không cần diễn tả thành vòng token. Với khóa \(k\) và tập nút \(V\), công thức khái quát:

\[
\boxed{\operatorname{owner}(k)=
\underset{v\in V}{\operatorname{argmax}}\ H(k,v).}
\]

Hàm \(H(k,v)\) tạo điểm xác định, phân bố đủ tốt cho cặp khóa–nút. Khi thêm nút \(u\), nếu \(H(k,u)\) không vượt điểm tốt nhất trước đó thì chủ cũ của \(k\) vẫn giữ nguyên; nếu vượt thì \(k\) chuyển đến \(u\). Với \(R\) bản sao, có thể chọn **\(R\) điểm cao nhất** theo cách không trùng nút vật lý.

Trong trường hợp có **hàng triệu khóa, hàng nghìn nút** và thường xuyên tra cứu qua ứng dụng, cấu trúc chỉ mục giúp tra token của vòng băm có thể hữu ích hơn việc tính điểm tất cả nút mỗi lần. Ngược lại, với số nút nhỏ hoặc cần quản lý trọng số và replica theo chính sách riêng, rendezvous hashing có thể đơn giản hơn. Không có giải pháp tối ưu cho mọi workload.

## 13. Điều kiện triển khai thực tế và những lỗi dễ mắc

**1. Dùng hàm băm không ổn định giữa tiến trình.** Một số ngôn ngữ hoặc thư viện cố tình ngẫu nhiên hóa hàm băm mặc định. Nếu mỗi máy tạo token khác nhau, cùng khóa sẽ được định tuyến khác nhau. Cần thuật toán băm, seed, cách mã hóa và phiên bản thống nhất.

**2. Nhầm giá trị hash với địa chỉ IP.** Token không nhất thiết phụ thuộc trực tiếp vào địa chỉ mạng. Nên dùng **định danh nút ổn định**; nếu máy đổi IP mà vẫn là cùng một nút logic, không nhất thiết phải thay mọi token.

**3. Thêm nút rồi cho đọc ngay lập tức.** Vòng băm chỉ xác định nơi **nên** lưu khóa. Dữ liệu cần được sao chép và xác minh trước khi nút mới có thể trả kết quả đúng.

**4. Không phân biệt nút vật lý khi chọn replica.** Nếu một nút có nhiều vnode, chọn ba token đầu tiên có thể chọn cả ba trên cùng một máy. Khi máy đó hỏng, cả ba “bản sao” đều biến mất.

**5. Nghĩ băm nhất quán tự bảo đảm tính nhất quán dữ liệu.** Đây là kỹ thuật **phân phối khóa**. Quorum, versioning, conflict resolution, sao chép và phát hiện lỗi là các vấn đề khác.

**6. Tin rằng số khóa đồng đều đồng nghĩa dung lượng và tải CPU đồng đều.** Kích thước dữ liệu mỗi khóa và độ nóng truy cập có thể khác nhau, gây hotspot.

**7. Quên vòng quay về 0.** Nếu giá trị băm của khóa lớn hơn token cuối, phải chọn token đầu tiên trên vòng.

**8. Xử lý token trùng nhau không nhất quán.** Với không gian hash hữu hạn, va chạm token về lý thuyết có thể xảy ra. Mọi máy phải có **quy tắc thứ tự phụ xác định**, hoặc hệ thống phải tạo lại token để giữ vị trí duy nhất.

**9. Đổi số vnode một cách tùy tiện.** Số vnode là một phần của cấu hình vòng. Đổi từ 64 thành 128 vnode cho mỗi nút sẽ tạo thêm nhiều token và đổi vị trí lưu của một số khóa, dù số nút vật lý giữ nguyên.

**10. Tái cân bằng mà không xử lý cập nhật trong lúc chuyển dữ liệu.** Nếu sao chép snapshot xong rồi chuyển tuyến mà bỏ qua ghi phát sinh sau snapshot, có thể làm mất cập nhật. Cần xử lý nhật ký và phiên bản hoặc một giao thức chuyển giao phù hợp.

**11. Đánh giá chỉ chi phí tính toán mà bỏ qua mạng và đĩa.** Tìm token nhanh không đảm bảo truy vấn nhanh nếu nút đích ở xa, quá tải hoặc cần nhiều lần đọc trang đĩa.

**12. Dùng cùng một nút vật lý cho mọi miền lỗi.** Replica đặt cùng rack hoặc cùng vùng có thể hỏng đồng thời. Cần mô hình **failure domain** và bố trí replica có chủ đích.

## 14. Câu hỏi và bài tập tự kiểm tra

### Câu 1. Chọn nút chủ trên vòng

Cho không gian băm 0–99, ba nút **A@10, B@40, C@80**. Xác định nút lưu khóa có giá trị băm **0, 10, 11, 40, 41, 80, 99**.

**Đáp án:**

| Giá trị băm | Nút chủ | Lý do |
| ---: | --- | --- |
| 0 | A | Token đầu tiên theo chiều kim đồng hồ là 10 |
| 10 | A | Bằng vị trí token A |
| 11 | B | Nằm trong \((10,40]\) |
| 40 | B | Bằng vị trí token B |
| 41 | C | Nằm trong \((40,80]\) |
| 80 | C | Bằng vị trí token C |
| 99 | A | Vượt token cuối 80, quay về token 10 |

### Câu 2. Thêm nút và tính phần chuyển giao

Thêm **D@60** vào vòng A@10, B@40, C@80. Những giá trị băm nào chuyển nút chủ? Khóa băm thành 53 và 65 được đặt ở đâu?

**Đáp án:** Các giá trị băm trong đoạn \((40,60]\) đổi từ C sang D. Khóa băm thành **53 chuyển từ C sang D**; khóa băm thành **65 vẫn ở C**. Những đoạn khác không thay đổi.

### Câu 3. Xóa nút sau khi đã thêm D

Từ vòng A@10, B@40, D@60, C@80, xóa B@40. Giá trị băm 35 đi từ đâu tới đâu?

**Đáp án:** Trước khi xóa, 35 thuộc B vì \(10<35\le40\). Sau khi xóa, token tiếp theo là D@60, nên 35 được gán lại cho **D**. Điều này không chứng minh D đã có dữ liệu: cần sao chép/khôi phục từ bản sao hoặc nguồn còn tồn tại.

### Câu 4. Công thức kỳ vọng khi thêm một nút

Giả sử có \(N=9\) nút ngang năng lực, token và khóa được phân bố độc lập, đều lý tưởng. Nếu thêm một nút thứ 10, tỷ lệ không gian khóa đổi chủ theo kỳ vọng là bao nhiêu?

**Đáp án:**

\[
\frac{1}{N+1}=\frac1{10}=10\%.
\]

Đó là **kỳ vọng theo mô hình**, không bảo đảm thực tế đúng 10% khi chỉ có ít vị trí ngẫu nhiên. Nếu có nhiều vnode phân bố tốt, độ lệch quanh kỳ vọng có thể nhỏ hơn.

### Câu 5. Chọn ba replica trên vòng vnode

Thứ tự token là **A1, A2, B1, C1, B2, A3, C2**. Khóa được ánh xạ vào trước A1. Hãy chọn ba nút vật lý phân biệt.

**Đáp án:** Gặp A1 → A, gặp A2 → bỏ qua (A đã chọn), gặp B1 → B, gặp C1 → C. Vậy ba replica là **A, B, C**, không phải A, A, B.

### Câu 6. Tính bộ nhớ metadata

Một cụm có **12 nút**, mỗi nút **32 vnode**. Có bao nhiêu token? Tra cứu trên một mảng token đã sắp xếp có độ phức tạp tiệm cận nào?

**Đáp án:**

\[
V=12\cdot32=384\text{ token}.
\]

Với tìm kiếm nhị phân, tra token đầu tiên không nhỏ hơn hash khóa tốn **\(O(\log384)\)** phép so sánh, tức **\(O(\log V)\)** theo số token. Chưa tính thời gian mạng và tra dữ liệu bên trong nút.

### Câu 7. Phân biệt định tuyến và nhất quán dữ liệu

Hai máy khách sử dụng vòng khác nhau khi một nút đang được thêm. Cả hai cùng ghi một khóa nhưng có thể đến hai máy khác nhau. Băm nhất quán đã đủ ngăn xung đột chưa?

**Đáp án:** **Chưa.** Băm nhất quán cho phép mỗi máy khách tính nút đích từ một phiên bản vòng cụ thể. Hệ thống vẫn cần cơ chế phối hợp **phiên bản thành viên, chuyển giao dữ liệu, ghi/đọc đồng thời, sao chép và giải quyết xung đột**.

### Câu 8. Băm nhất quán có giải quyết mọi dạng mất cân bằng không?

Giả sử hai nút mỗi nút giữ 50% số khóa, nhưng một khóa trên A chiếm 90% lượt đọc. Có thể chỉ tăng số vnode để tự cân bằng tải không?

**Đáp án:** Không chắc. Băm lại có thể làm **khóa nóng** chuyển sang nút khác, nhưng một khóa đơn lẻ vẫn không tự được chia nhiều đường xử lý. Cần cache, nhân bản phục vụ đọc, chia nhỏ đơn vị dữ liệu hoặc chiến lược xử lý hotspot phù hợp.

## 15. Tổng kết

**Băm nhất quán** đặt token nút và khóa trong một **không gian băm vòng**. Với một khóa, hệ thống chọn **token đầu tiên theo chiều kim đồng hồ**, xử lý quay vòng nếu vượt token cuối. Khi thêm hoặc xóa một nút, chỉ những đoạn khóa liên quan thay đổi chủ, giúp **giảm đáng kể lượng dữ liệu phải tái phân phối** so với cách chia dư trực tiếp theo số nút.

Để vận hành ở quy mô thực tế, cần thêm **virtual nodes** nhằm giảm lệch phân bố, chọn **replica trên các nút vật lý phân biệt**, đồng bộ phiên bản thành viên và triển khai **sao chép dữ liệu thực sự** khi thay đổi vòng. Băm nhất quán **không tự giải quyết** tính nhất quán đọc–ghi, phát hiện lỗi, hotspot hay phân bố replica theo miền sự cố.

Khi đánh giá cấu trúc cho một bài toán phân tán, hãy xét đồng thời **độ phức tạp tra token \(O(\log V)\)**, metadata \(O(V)\), tỷ lệ khóa cần chuyển theo kỳ vọng, băng thông tái cân bằng, chất lượng hàm băm, dung lượng nút và yêu cầu sẵn sàng của hệ thống.
