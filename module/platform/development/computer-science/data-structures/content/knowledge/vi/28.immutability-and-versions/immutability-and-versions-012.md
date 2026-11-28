# Phân biệt lưu phiên bản với ghi bền dữ liệu xuống thiết bị lưu trữ

## 1. Hai vấn đề thường bị gọi chung là “lưu dữ liệu”

Giả sử ứng dụng quản lý giỏ hàng. Khi người dùng thêm một sản phẩm, ứng dụng cần giải quyết hai câu hỏi khác nhau:

1. **Làm thế nào để vẫn truy cập được trạng thái giỏ hàng trước khi sửa?** Đây là vấn đề **lưu phiên bản** của cấu trúc dữ liệu (*versioning*, *persistent data structure*).
2. **Làm thế nào để sau khi mất điện hoặc khởi động lại máy, trạng thái đã xác nhận vẫn còn?** Đây là vấn đề **ghi bền dữ liệu** (*durability*) xuống thiết bị lưu trữ.

Hai yêu cầu có thể cùng tồn tại, nhưng **không suy ra nhau**. Một cây bất biến có nhiều phiên bản trong RAM sẽ mất khi tiến trình kết thúc nếu chưa có cơ chế lưu bền. Ngược lại, một tệp hay cơ sở dữ liệu có thể giữ trạng thái mới nhất trên đĩa qua lần khởi động lại mà không cho phép truy cập lại các phiên bản cũ.

Trong chương **Bất biến và phiên bản** của nền tảng cấu trúc dữ liệu, ta nghiên cứu cách lưu trạng thái cũ bằng mảng, danh sách liên kết, cây và kỹ thuật chia sẻ cấu trúc; đồng thời cần phân biệt rõ phần đó với bài toán lưu trữ, lỗi hệ thống và khôi phục sau sự cố.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **immutable**, **persistent**, **snapshot**, **version history** và **durable**.
- Giải thích bất biến chia sẻ cấu trúc và vì sao giữ các gốc phiên bản không có nghĩa chúng đã được ghi xuống đĩa.
- Nhận diện các tầng từ bộ nhớ ứng dụng đến bộ đệm hệ điều hành và thiết bị lưu trữ.
- Mô tả vai trò của serialization, thao tác thay tệp nguyên tử, `fsync`, write-ahead log và recovery.
- Lựa chọn thiết kế dựa trên nhu cầu undo, đọc nhất quán, khởi động lại, kiểm toán và ngân sách thời gian/bộ nhớ.

## 2. Phân biệt năm thuật ngữ

| Thuật ngữ | Ý nghĩa trực tiếp | Điều **không** được bảo đảm |
|---|---|---|
| **Immutable** (bất biến) | Đối tượng không bị thay đổi qua giao diện đã thiết kế sau khi tạo | Không tự lưu bản cũ khi không còn tham chiếu; không tự ghi xuống đĩa |
| **Persistent data structure** (cấu trúc dữ liệu lưu phiên bản) | Cập nhật tạo phiên bản mới, phiên bản cũ vẫn có thể sử dụng | Không mặc nhiên có khả năng tồn tại sau khi tiến trình mất |
| **Snapshot** (ảnh chụp trạng thái) | Biểu diễn trạng thái ở một thời điểm hoặc phiên bản cụ thể | Có thể chỉ ở RAM; chưa chắc đã được đồng bộ ra thiết bị |
| **Version history** (lịch sử phiên bản) | Tập hợp các phiên bản/trạng thái đã giữ cùng quy tắc truy cập | Không nhất thiết vĩnh viễn hoặc chống mất mát dữ liệu |
| **Durability** (tính bền vững sau sự cố) | Một cập nhật đã được xác nhận theo hợp đồng lưu trữ vẫn có thể phục hồi sau loại lỗi được hệ thống cam kết chịu được | Không đồng nghĩa giữ mọi phiên bản cũ, sao lưu ngoại tuyến hay chống mọi loại hỏng hóc |

Từ `persistent` dễ gây nhầm lẫn nhất. Trong lý thuyết cấu trúc dữ liệu, “persistent” thường nghĩa là **phiên bản cũ còn dùng được**. Trong tài liệu hệ thống lưu trữ, “persistence” lại thường được dùng cho việc **dữ liệu được giữ qua lần khởi động lại**. Khi thiết kế API nên nói rõ `versioned in memory` hay `durable on disk` thay vì chỉ ghi chung “persistent”.

### Ma trận hai chiều: độc lập với nhau

| | Chưa ghi bền | Đã có cơ chế ghi bền |
|---|---|---|
| **Không giữ phiên bản cũ** | Một biến/mảng thay đổi trực tiếp trong RAM | Tệp hoặc DB chỉ giữ trạng thái mới nhất; các lần ghi trước có thể bị thay thế |
| **Có giữ phiên bản cũ** | Cây bất biến với nhiều root trong RAM | Lịch sử giao dịch hoặc các snapshot được ghi, xác nhận và có thể khôi phục |

Hình dung một bộ soạn thảo có 20 bước **undo** trong bộ nhớ: đó là lưu phiên bản, nhưng ứng dụng bị tắt đột ngột vẫn có thể mất toàn bộ 20 bước. Một ứng dụng khác tự lưu **chỉ bản mới nhất** xuống thiết bị sau mỗi thao tác: nó có durability cho bản đã xác nhận nhưng có thể không undo được.

## 3. Lưu phiên bản trong RAM: bất biến và chia sẻ cấu trúc

Một cấu trúc dữ liệu lưu phiên bản không nhất thiết sao chép toàn bộ dữ liệu sau mỗi cập nhật. Với **structural sharing** (chia sẻ cấu trúc), phiên bản mới tái sử dụng các nút không thay đổi của phiên bản cũ.

Ví dụ danh sách liên kết bất biến:

```text
V1 (root) ──► [B] ──► [A] ──► None

V2 (root) ──► [C] ──► [B] ──► [A] ──► None
                        ▲
                        │
                cùng node [B] trong V1
```

Thêm `C` ở đầu tạo **một nút mới**. Gốc `V1` vẫn trỏ đến `B`; gốc `V2` trỏ đến `C`, và `C` trỏ đến đúng nút `B` cũ. Không cần sao chép `A` hay `B`.

**Bất biến:** các nút đã được chia sẻ không bao giờ bị sửa theo đường đi từ phiên bản mới. Nếu một nút chia sẻ bị đột ngột sửa, cả phiên bản cũ lẫn phiên bản mới có thể thay đổi và làm hỏng ngữ nghĩa lịch sử.

### 3.1. Ví dụ Python: stack bất biến có các phiên bản

```python
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Node:
    value: str
    next: Optional["Node"] = None


def push(head: Optional[Node], value: str) -> Node:
    return Node(value, head)  # tao node moi; khong sua head


def pop(head: Optional[Node]) -> Optional[Node]:
    if head is None:
        raise IndexError("stack rong")
    return head.next


def values(head: Optional[Node]) -> list[str]:
    result = []
    while head is not None:
        result.append(head.value)
        head = head.next
    return result


v0 = None
v1 = push(v0, "A")
v2 = push(v1, "B")
v3 = push(v2, "C")

assert values(v2) == ["B", "A"]
assert values(v3) == ["C", "B", "A"]
assert v3.next is v2          # chia se cung doi tuong Node
assert pop(v3) is v2          # quay lai v2 trong O(1)
```

Kết quả cho thấy `v2` và `v3` cùng tồn tại. Tuy nhiên, cả hai chỉ là **tham chiếu trong bộ nhớ**. Không có dòng mã nào ở trên mở tệp hay gọi cơ chế ghi bền. Tắt tiến trình không làm các nút này tự xuất hiện trở lại.

Lưu ý về Python: `@dataclass(frozen=True)` giúp ngăn gán lại thuộc tính thông qua cách sử dụng thông thường. Nếu thuộc tính bên trong chứa một đối tượng **có thể thay đổi**, tính bất biến sâu (*deep immutability*) không tự được bảo đảm; ví dụ nên dùng các giá trị và liên kết bất biến như trên.

### 3.2. Cập nhật ở giữa cây: path copying

Với cây tìm kiếm nhị phân bất biến, thêm khóa vào một nhánh thường tạo lại các nút **trên đường từ gốc đến vị trí cập nhật** và chia sẻ toàn bộ các nhánh không bị chạm tới:

```text
Phiên bản V1:                Phiên bản V2 (chèn 12):

          [10]                        [10']
         /    \                      /     \
       [5]    [15]                 [5]     [15']
              /  \                        /    \
            [11] [20]                   [11']  [20]
                                            \
                                            [12]

[5] và [20] được chia sẻ; các nút có dấu ' là nút mới.
```

Nếu chiều cao cây là `h`, cập nhật kiểu path copying thường tốn `O(h)` thời gian và tạo `O(h)` nút mới; tra cứu một phiên bản vẫn tốn `O(h)`. Với cây cân bằng, `h = O(log n)`, còn cây tìm kiếm nhị phân không cân bằng có thể đạt `h = O(n)`.

Điều này giải thích vì sao một thiết kế giữ nhiều phiên bản có thể tiết kiệm đáng kể bộ nhớ so với sao chép toàn bộ cây sau mỗi thay đổi. Mặt khác, nó vẫn tiêu tốn thêm nút, đối tượng root, bộ nhớ cho metadata và thời gian thu gom rác.

### 3.3. Giữ tham chiếu và vòng đời phiên bản

Tạo cấu trúc bất biến **không tự giữ lịch sử mãi mãi**. Nếu ứng dụng chỉ duy trì `current_root` và thay nó bằng root mới, rồi không ai giữ root cũ, các nút không còn được tham chiếu có thể được bộ thu gom rác thu hồi.

Để có lịch sử, ứng dụng cần quản lý bảng phiên bản:

```text
versions[101] -> root_v101
versions[102] -> root_v102
versions[103] -> root_v103
```

Chính sách giữ 10, 100 hay tất cả phiên bản là **quyết định của ứng dụng**. Snapshot chia sẻ cấu trúc giúp giảm chi phí sao chép, nhưng số phiên bản được giữ và mức độ thay đổi quyết định lượng bộ nhớ tăng theo thời gian.

## 4. Ghi bền dữ liệu: đi qua nhiều tầng bộ nhớ

Khi ứng dụng “ghi tệp”, dữ liệu không nhất thiết đã ngay lập tức nằm trên thiết bị lưu trữ phi mất dữ liệu. Một đường đi được đơn giản hóa:

```text
Phiên bản trong RAM của ứng dụng
         |
         v
   Serialize thành bytes
         |
         v
  Bộ đệm của thư viện/ngôn ngữ
         |
         v
  Bộ đệm trang của hệ điều hành
         |
         v
  File system / driver / cache thiết bị
         |
         v
  Thiết bị lưu trữ phi mất dữ liệu
```

Các bước này trả lời những câu hỏi khác với cấu trúc bất biến:

| Bước | Mục đích | Vì sao chưa đủ để khẳng định durability? |
|---|---|---|
| `serialize` | Chuyển object graph sang bytes có định dạng rõ ràng | Mới tạo biểu diễn, chưa chắc có I/O |
| `write` | Đưa bytes vào luồng ghi của hệ điều hành/thư viện | Có thể mới vào bộ đệm |
| `flush` của đối tượng tệp | Chuyển bộ đệm trong tiến trình xuống hệ điều hành | Thường chưa buộc thiết bị hoàn tất ghi bền |
| `fsync` / cơ chế sync tương đương | Yêu cầu hệ thống đồng bộ nội dung và metadata liên quan của tệp | Bảo đảm thực tế phụ thuộc OS, file system, thiết bị và hợp đồng lưu trữ |
| Ghi/đồng bộ metadata thư mục | Giữ bền việc thêm, đổi tên hoặc thay thế tên tệp | Dữ liệu tệp bền nhưng đường dẫn mới chưa chắc bền nếu metadata chưa đồng bộ |

**Serialize không đồng nghĩa với lưu bền.** Gọi `json.dumps` tạo một chuỗi trong RAM; gọi `json.dump` có ghi ra file nhưng vẫn có thể dừng trước khi dữ liệu an toàn theo hợp đồng của hệ thống. Ngay cả khi lệnh ghi trả về thành công, cần hiểu chính xác cam kết “đã ghi” ở tầng lưu trữ đang dùng.

Ví dụ, ghi file vào một thư mục trên ổ đĩa cục bộ và ghi lên hệ thống lưu trữ mạng có thể có bảo đảm khác nhau. Các thiết bị có cache dễ mất dữ liệu khi mất điện hoặc hệ thống cấu hình không tuân thủ flush có thể không đáp ứng kỳ vọng dù ứng dụng đã gọi đúng API.

## 5. Atomicity, durability và crash consistency không giống nhau

Ba yêu cầu thường đi cùng nhưng độc lập:

- **Atomicity:** thao tác được nhìn thấy như xảy ra toàn bộ hoặc không xảy ra; không lộ trạng thái nửa cũ nửa mới trong phạm vi bảo đảm.
- **Durability:** trạng thái đã xác nhận còn có thể phục hồi sau sự cố trong phạm vi loại lỗi được cam kết.
- **Crash consistency:** sau sự cố giữa chừng, dữ liệu còn ở một trạng thái có thể nhận biết và phục hồi, không bị hỏng cấu trúc logic ngoài hợp đồng hệ thống.

Giả sử ứng dụng đang lưu `V7` và muốn đưa `V8` thành phiên bản hiện hành:

```text
V7: { "balance": 100 }
V8: { "balance": 120 }
```

Nếu mở ngay tệp hiện hành và ghi đè, tiến trình chết giữa lúc ghi có thể để lại một nội dung không phải `V7` cũng không phải `V8`. Một kỹ thuật phổ biến cho **snapshot nhỏ, lưu trong một tệp** là:

1. Serialize toàn bộ trạng thái `V8` ra **tệp tạm cùng hệ thống tệp**.
2. Ghi hết bytes rồi flush bộ đệm ngôn ngữ và đồng bộ tệp tạm (`fsync` hoặc API tương đương).
3. **Thay thế tên tệp hiện hành** bằng tệp tạm bằng phép đổi tên/thay thế có tính nguyên tử theo bảo đảm của nền tảng.
4. Nếu nền tảng cần, đồng bộ metadata của thư mục chứa tệp để tên mới tồn tại qua sự cố.
5. Chỉ thông báo cập nhật đã được commit sau khi các bước bắt buộc theo hợp đồng lưu trữ thành công.

Với hệ thống tệp và API hỗ trợ atomic replace, người đọc sẽ thấy `V7` hoặc `V8`, thay vì nửa nội dung của mỗi bản. Tuy nhiên, **atomic replace không tự đồng nghĩa với durable replace**: sự thay đổi tên tệp có thể chưa được đồng bộ bền. Chi tiết kỹ thuật phải theo tài liệu của OS/file system; trên một số nền tảng, việc đồng bộ thư mục hoặc tính nguyên tử của thao tác đổi tên có giới hạn riêng.

### 5.1. Ví dụ Python: lưu snapshot ra một tệp

Đoạn mã minh họa một cách ghi **toàn bộ snapshot JSON** cho dữ liệu nhỏ, không phải trình quản lý giao dịch hay cơ sở dữ liệu hoàn chỉnh:

```python
import json
import os
import tempfile
from pathlib import Path


def save_snapshot(path: str, snapshot: dict) -> None:
    target = Path(path)
    payload = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")

    # Tao tep tam trong cung thu muc de tranh di chuyen khac filesystem.
    fd, tmp_path = tempfile.mkstemp(
        prefix="." + target.name + ".",
        suffix=".tmp",
        dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()             # thu vien -> OS
            os.fsync(stream.fileno())  # yeu cau dong bo tep

        os.replace(tmp_path, target)   # thay ten tep khi he thong ho tro

        # Tren POSIX: dong bo metadata thu muc neu API/filesystem ho tro.
        if os.name == "posix":
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        # Neu replace da thanh cong, tmp_path co the khong con ton tai.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def load_snapshot(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


versions = {
    "v1": ["B", "A"],
    "v2": ["C", "B", "A"]
}
save_snapshot("stack-versions.json", versions)
restored = load_snapshot("stack-versions.json")
assert restored["v1"] == ["B", "A"]
assert restored["v2"] == ["C", "B", "A"]
```

**Giới hạn quan trọng:** đoạn mã không hỗ trợ đồng thời nhiều tiến trình ghi, khóa giao dịch, phát hiện dữ liệu lỗi, phục hồi tự động, checksum, quản lý phiên bản schema hay sao lưu. Nó giả định tệp nằm trên hệ thống có bảo đảm thao tác thay thế phù hợp; việc đồng bộ thư mục ở trên chỉ minh họa trên POSIX và có thể thất bại hoặc không được hỗ trợ. Đối với Windows và các hệ thống tệp khác, cần chọn API và quy trình durability theo tài liệu nền tảng; đừng suy ra tính an toàn chỉ từ `os.replace`.

Trong ví dụ, nội dung JSON giữ hai phiên bản `v1` và `v2` vì **ta chủ động serialize cả hai**. Nếu chỉ serialize `v2`, tệp sẽ không tự chứa `v1`. Việc đọc lại JSON cũng không tự tái lập quan hệ **chia sẻ cùng đối tượng Node** như ở ví dụ stack; muốn bảo toàn object graph và structural sharing qua lần khởi động lại cần định dạng lưu node-ID, liên kết và root-ID phù hợp.

## 6. Write-ahead log: ghi nhật ký trước khi thay đổi dữ liệu

Ghi lại cả snapshot sau **mỗi** cập nhật có thể quá tốn kém: với cấu trúc kích thước `n`, mỗi lần serialize toàn bộ mất thời gian và I/O `O(n)`, dù thay đổi chỉ là một phần tử.

Một hệ thống lưu trữ có thể dùng **write-ahead log (WAL)**:

1. Ghi một bản ghi mô tả thay đổi hoặc giao dịch vào log theo định dạng có thể kiểm tra.
2. Trước khi xác nhận commit bền, bảo đảm **bản ghi commit và các log cần thiết** đã bền theo chính sách hệ thống.
3. Sau đó, các trang dữ liệu hay snapshot chính có thể được cập nhật vào lúc thích hợp.
4. Khi khởi động lại sau sự cố, đọc checkpoint/snapshot gần nhất rồi **replay các giao dịch đã commit** từ log để phục hồi.

```text
Thời điểm        RAM/cấu trúc phiên bản           Lưu trữ

t0               V0                               checkpoint V0
t1               V1                               WAL: thay đổi V0->V1
t2               V2                               WAL: thay đổi V1->V2
t3               thông báo commit V2              log commit V2 đã được sync
t4               ghi checkpoint mới               checkpoint V2 (khi hoàn tất)

Crash sau t3 -> khôi phục checkpoint + log đã commit tới V2
```

**Nguyên tắc “write-ahead”:** log liên quan đến một thay đổi phải được ghi bền theo đúng thứ tự trước khi cho phép trang dữ liệu phụ thuộc vào thay đổi đó trở thành bản trên đĩa mà recovery không xử lý được. Một thiết kế WAL đúng cần thêm quy tắc **commit marker**, thứ tự ghi, phát hiện bản ghi chưa hoàn tất, idempotency/replay, kiểm tra checksum và cắt log sau checkpoint.

WAL không tự tạo khả năng undo/redo cấp ứng dụng theo mọi phiên bản đã từng tồn tại. Một log có thể bị cắt bỏ sau checkpoint và chỉ phục vụ phục hồi trạng thái **đã commit mới nhất**. Ngược lại, ứng dụng có thể giữ mọi phiên bản cho mục đích lịch sử nhưng vẫn chưa có WAL hoặc snapshot nào được ghi bền.

### 6.1. Copy-on-write trên đĩa

Khái niệm **copy-on-write (COW)** xuất hiện cả trong cấu trúc phiên bản và hệ thống lưu trữ, nhưng hai mục tiêu cần tách bạch.

Ở cây bất biến trong RAM, path copying tạo nút mới để **giữ phiên bản cũ không bị sửa**. Trong một hệ thống lưu trữ COW, khi cập nhật một trang, hệ thống có thể ghi trang mới vào vị trí khác, đồng bộ nội dung rồi cập nhật con trỏ root/metadata theo giao thức commit; cách này giúp tránh ghi đè dữ liệu cũ trước khi phiên bản mới an toàn.

COW **có thể** được dùng để xây hệ thống vừa hỗ trợ snapshot/phiên bản vừa crash-consistent, nhưng phải có:

- Cơ chế phân biệt trang cũ và trang mới bằng địa chỉ/ID.
- Thứ tự ghi trang con trước khi commit con trỏ root tham chiếu tới chúng.
- Bản ghi gốc hoặc metadata commit được cập nhật an toàn.
- Cơ chế khôi phục và thu hồi các trang không còn được root hợp lệ tham chiếu.

Chỉ sử dụng các object bất biến ở tầng ứng dụng **không** bảo đảm thứ tự I/O hoặc trạng thái commit trên đĩa.

## 7. Tác động đến MVCC, snapshot, undo và backup

**MVCC (Multi-Version Concurrency Control)** là cơ chế thường thấy ở cơ sở dữ liệu cho phép một giao dịch đọc phiên bản phù hợp với snapshot của nó trong khi giao dịch khác cập nhật dữ liệu. Điều này liên quan đến **visibility** và **isolation**; durability của các giao dịch commit lại phụ thuộc cơ chế log, flush, replication và chính sách commit cụ thể.

| Tính năng | Điều cần thiết | Không nên suy ra |
|---|---|---|
| **Undo trong một tiến trình** | Giữ các root/version cũ và một chính sách lịch sử | Đã ghi bền qua sự cố |
| **Đọc snapshot nhất quán** | Định nghĩa thời điểm chụp và phiên bản mà người đọc thấy | Mọi snapshot đều là bản sao lưu bền |
| **Time travel query** | Duy trì lịch sử dữ liệu đủ lâu và API truy vấn theo phiên bản | Lịch sử không bao giờ bị dọn dẹp |
| **Durable commit** | Giao thức lưu bền và phục hồi theo hợp đồng của hệ thống | Có thể truy vấn lại mọi phiên bản cũ |
| **Backup** | Bản sao có thể phục hồi và được kiểm tra, thường ở miền lỗi riêng | Snapshot cục bộ chắc chắn sống sót khi ổ đĩa mất |

Một snapshot trên cùng ổ đĩa hữu ích để khôi phục lỗi logic nhanh, nhưng có thể mất cùng ổ khi phần cứng hỏng. **Backup** cần có chính sách tách miền lỗi, thời gian lưu, xác minh nội dung và kiểm tra khôi phục.

Ngoài ra cần phân biệt **rollback ứng dụng** với **rollback giao dịch**. Đổi root từ `V3` về `V2` chỉ thay phiên bản đang được dùng; nếu `V3` đã ghi bền và được hệ thống khác quan sát, “quay lại” có thể phải tạo một giao dịch bù (*compensating transaction*) mới. Không thể coi việc trỏ lại root cũ là tự động đảo mọi tác dụng phụ bên ngoài.

## 8. Kịch bản sự cố: phiên bản nào còn sau khi khởi động lại?

Giả sử hệ thống có các trạng thái `V0 → V1 → V2`. Ứng dụng vừa tạo `V2` trong RAM:

| Thời điểm gặp lỗi | Điều đã hoàn tất | Kỳ vọng đúng |
|---|---|---|
| Ngay sau khi tạo root `V2` trong RAM | Chưa serialize hoặc ghi | Mất `V2` khi tiến trình mất RAM; `V0/V1` cũng chỉ còn nếu đã lưu bền hoặc tái tạo được |
| Sau `write` nhưng chưa có đồng bộ bắt buộc | Có thể còn ở bộ đệm OS | Không được hứa `V2` sống sót khi mất điện |
| Sau khi sync tệp tạm nhưng trước khi thay tên | Bytes của tệp tạm có thể đã bền | Tệp hiện hành thường vẫn là `V1`; tệp tạm có thể cần dọn |
| Sau khi thay tên nhưng chưa đồng bộ metadata thư mục khi cần | Tên tệp mới đã được quan sát | Sau crash có thể không giữ bền thao tác thay tên, tùy hệ thống |
| Sau khi toàn bộ giao thức commit bền kết thúc | Trạng thái xác nhận theo hợp đồng lưu trữ | `V2` phải phục hồi được trong phạm vi lỗi được hệ thống cam kết |

Không nên mô tả “đã gọi `fsync` là chắc chắn không thể mất dữ liệu” mà bỏ qua file system, thiết bị, cấu hình cache và miền lỗi. Với hệ thống phân tán, durability còn phụ thuộc số bản sao và thời điểm xác nhận quorum; sao chép tới RAM của nhiều máy không đồng nghĩa đã lưu bền ở các máy ấy.

### Ví dụ quy trình khôi phục

Một dịch vụ dùng checkpoint `V100` và log bền chứa các giao dịch đã commit `101, 102, 103`. Sau khi khởi động lại:

1. Đọc checkpoint có checksum/phiên bản hợp lệ gần nhất.
2. Kiểm tra tính liên tục và tính hợp lệ của các bản ghi log.
3. Replay các bản ghi được xác nhận commit theo đúng thứ tự, bỏ qua hoặc hoàn tác giao dịch chưa hoàn tất theo thiết kế.
4. Thu được trạng thái mới nhất được cam kết, ví dụ `V103`.
5. Tùy chính sách, khôi phục **bảng các root lịch sử** hoặc chỉ root `V103`.

Việc phục hồi `V103` **không chứng minh** các root `V101`, `V102` còn truy vấn được. Muốn hỗ trợ time travel sau khởi động lại, định dạng lưu trữ và retention phải giữ đủ dữ liệu để dựng lại từng phiên bản cần thiết.

## 9. Chi phí thời gian và bộ nhớ: đừng chỉ nhìn Big-O trong RAM

| Thiết kế | Chi phí cập nhật gần đúng | Chi phí lưu trữ | Đặc điểm nổi bật |
|---|---|---|---|
| Stack bất biến dạng linked list | `O(1)` và 1 nút mới mỗi `push` | `O(1)` nút mới mỗi phiên bản được giữ | Undo nhanh nếu còn root |
| Cây bất biến dùng path copying | `O(h)` thời gian và nút mới mỗi lần sửa | `O(h)` nút mới/cập nhật; cây cân bằng `h = O(log n)` | Chia sẻ phần không đổi |
| Snapshot đầy đủ xuống file | Thường `O(S)` bytes và thời gian serialize/ghi cho trạng thái kích thước `S` | Có thể `O(VS)` cho `V` snapshot đầy đủ | Đọc/khôi phục snapshot đơn giản |
| Log thay đổi/WAL | Chi phí phụ thuộc kích thước bản ghi thay đổi và đồng bộ commit | Tăng theo log cho đến khi checkpoint/cắt tỉa | Ghi cập nhật nhỏ, cần recovery |
| COW page/tree trên lưu trữ | Phụ thuộc số trang thay đổi và chiều cao chỉ mục | Giữ trang cũ theo snapshot đang sống | Phối hợp versioning với commit |

Ký hiệu `S` là kích thước trạng thái đã serialize; `h` là chiều cao cấu trúc; `V` là số phiên bản cần giữ. Các con số này chưa tính cache, căn chỉnh trang, phân mảnh, nén, độ trễ `fsync` hoặc ghi lặp do lỗi.

**Độ phức tạp Big-O không thay thế chi phí I/O.** Hai phương án đều tạo `O(log n)` nút mới có thể có thời gian thực khác nhau rất xa nếu một phương án chỉ cấp phát RAM còn phương án kia phải ghi và đồng bộ nhiều trang SSD trước khi trả kết quả cho người dùng.

### 9.1. Garbage collection và retention

Giữ mọi phiên bản vĩnh viễn thường khiến bộ nhớ hoặc dung lượng lưu trữ tăng. Một chính sách thực tế cần trả lời:

- Giữ bao nhiêu phiên bản, theo thời gian hay theo số lượng?
- Ai đang đọc phiên bản cũ và khi nào có thể giải phóng các nút/trang chỉ còn được tham chiếu bởi phiên bản ấy?
- Sau checkpoint, bản ghi log nào không còn cần cho recovery hoặc audit?
- Có yêu cầu pháp lý, kiểm toán hoặc bảo mật buộc phải giữ/xóa dữ liệu theo hạn định không?

Dọn root phiên bản cũ có thể làm giải phóng các nút chỉ thuộc về phiên bản đó; các nút được chia sẻ với phiên bản còn sống phải tiếp tục được giữ. Trên đĩa, cần cơ chế tham chiếu trang hoặc thu gom rác tương tự để không xóa dữ liệu mà một snapshot còn sử dụng.

## 10. Chọn giải pháp theo yêu cầu ứng dụng

### Trường hợp A: ứng dụng vẽ sơ đồ có undo/redo

Nếu người dùng chỉ cần undo trong khi ứng dụng đang mở, cấu trúc bất biến với root lịch sử có thể đáp ứng tốt, giảm chi phí sao chép bằng structural sharing. Nhưng nếu muốn mở lại sau khi mất điện mà vẫn undo được, cần **serialize và commit bền** cả lịch sử cần khôi phục, hoặc một nhật ký hành động đủ để tái tạo.

### Trường hợp B: dịch vụ tài chính chỉ cần số dư mới nhất sau restart

Yêu cầu chính là **durable commit**, thứ tự giao dịch, idempotency và recovery. Dịch vụ có thể dùng dữ liệu mutable trong RAM rồi dựa trên WAL/transaction của cơ sở dữ liệu để bền vững; không bắt buộc dùng cấu trúc dữ liệu functional persistent trong ứng dụng.

### Trường hợp C: hệ thống phân tích cần time travel theo ngày

Yêu cầu vừa có **nhiều phiên bản lịch sử** vừa có **durability**. Có thể dùng snapshot theo ngày, log thay đổi giữa các snapshot và chính sách giữ/xóa lịch sử. Hệ thống phải xác định rõ phiên bản nào đã hoàn tất và nhất quán trên tất cả các shard; chỉ có nhiều root trong RAM là chưa đủ.

### Trường hợp D: cache trong RAM tái dựng được từ nguồn gốc

Nếu cache có thể dựng lại an toàn và chi phí phục hồi chấp nhận được, không nhất thiết phải ghi bền cache. Dù vậy, dữ liệu gốc cần có cơ chế durability riêng; việc cache sử dụng cấu trúc bất biến chỉ là lựa chọn tổ chức và đồng bộ truy cập.

| Câu hỏi thiết kế | Khi câu trả lời là “có” |
|---|---|
| Có cần undo, so sánh trạng thái cũ, đọc snapshot đồng thời? | Cân nhắc **lưu phiên bản / structural sharing / MVCC** |
| Sau khởi động lại có phải giữ cập nhật đã xác nhận? | Cần **durable commit và recovery** |
| Có cần truy vấn lại phiên bản của tuần trước sau restart? | Cần **lưu bền lịch sử**, không chỉ snapshot mới nhất |
| Có cần phục hồi khi mất cả thiết bị? | Cần **backup/replication theo miền lỗi**, không chỉ `fsync` cục bộ |
| Dữ liệu có thể tái dựng rẻ từ nguồn bền? | Có thể không cần lưu bền lớp cache/phiên bản tạm |

## 11. Những nhầm lẫn thường gặp

1. **“Immutable nghĩa là dữ liệu không thể mất.”** Sai. Immutable chỉ nói về khả năng thay đổi đối tượng, không nói về nơi lưu hay loại lỗi chịu được.
2. **“Persistent data structure đã lưu xuống disk.”** Sai trong cách dùng thuật ngữ cấu trúc dữ liệu: các phiên bản có thể chỉ sống trong RAM.
3. **“Snapshot luôn là bản backup.”** Sai. Snapshot có thể ở cùng ổ và cùng miền lỗi; backup cần cơ chế bảo vệ và phục hồi riêng.
4. **“Gọi `write()` thành công là đã ghi bền.”** Không nhất thiết. Cần biết tầng bộ đệm và hợp đồng đồng bộ.
5. **“Atomic rename làm thao tác bền sau mất điện.”** Atomicity và durability là hai thuộc tính khác nhau; metadata cũng có thể cần đồng bộ.
6. **“Có WAL là có thể xem mọi phiên bản cũ.”** Không. Log có thể chỉ phục vụ crash recovery và bị cắt sau checkpoint.
7. **“Giữ root cũ là undo được mọi việc.”** Không. Tác dụng phụ như gửi tiền, gửi email hoặc ghi vào dịch vụ khác phải được xử lý ở tầng giao dịch/nghiệp vụ.
8. **“Cây persistent luôn rẻ hơn sao chép.”** Thường tiết kiệm khi thay đổi nhỏ và có nhiều phần chia sẻ, nhưng overhead nút, con trỏ, bộ nhớ cache và retention có thể đáng kể.

## 12. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng có các root `R1, R2, R3` trong RAM, người dùng undo từ `R3` về `R2`. Sau khi tiến trình mất điện, tất cả root biến mất. Cấu trúc đã “persistent” chưa?

**Đáp án:** Có theo nghĩa **cấu trúc dữ liệu lưu phiên bản** vì root cũ dùng được trước khi tiến trình mất. Chưa có bảo đảm **durable** vì root không được ghi bền hoặc tái tạo từ dữ liệu bền.

**Câu 2.** Một cơ sở dữ liệu xác nhận giao dịch mới nhất rồi phục hồi sau restart, nhưng không cho truy vấn trạng thái trước giao dịch. Nó có durability và version history không?

**Đáp án:** Có thể có durability cho giao dịch đã commit mà **không giữ lịch sử phiên bản có thể truy vấn**. Hai tính chất độc lập.

**Câu 3.** Trong cây nhị phân bất biến cân bằng có `n` khóa, cập nhật một khóa bằng path copying thường tạo bao nhiêu nút mới?

**Đáp án:** `O(log n)` nút trên đường sửa; những nhánh không đổi được chia sẻ. Với cây không cân bằng, chi phí có thể lên `O(n)`.

**Câu 4.** Vì sao gọi `json.dumps(obj)` rồi giữ chuỗi JSON trong RAM không bảo đảm dữ liệu sống sót sau mất điện?

**Đáp án:** Vì serialize chỉ tạo biểu diễn bytes/chuỗi; chưa có thao tác lưu bền trên thiết bị hoặc cơ chế phục hồi.

**Câu 5.** Đã `fsync` tệp tạm rồi `os.replace` sang tên hiện hành, nhưng chưa đồng bộ metadata thư mục trên nền tảng yêu cầu bước đó. Có được hứa tên tệp mới chắc chắn còn sau crash không?

**Đáp án:** Không. Nội dung tệp có thể đã được đồng bộ, nhưng thay đổi tên/entry trong thư mục chưa chắc bền theo hợp đồng nền tảng.

**Câu 6.** Hệ thống có WAL ghi bền đến giao dịch `T50` và checkpoint ở `T45`. Nếu crash, phải làm gì để phục hồi trạng thái?

**Đáp án:** Đọc checkpoint `T45`, xác minh log và replay các giao dịch **đã commit hợp lệ** từ `T46` đến `T50` theo giao thức recovery. Các bản ghi chưa commit hoặc hỏng phải được xử lý theo quy tắc của hệ thống.

**Câu 7.** Tại sao giữ mỗi root `latest` trên đĩa không đủ để khôi phục lịch sử undo của 100 phiên bản trước?

**Đáp án:** Vì không giữ các root cũ hoặc dữ liệu log cần để dựng lại chúng. Việc có một bản mới nhất bền vững không chứng minh lịch sử cũng còn.

**Câu 8.** Một snapshot nằm trên cùng thiết bị với cơ sở dữ liệu gốc. Nếu thiết bị hỏng hoàn toàn, snapshot có chắc còn không?

**Đáp án:** Không. Snapshot không thay thế backup/replication trên miền lỗi độc lập.

## Kết luận

**Lưu phiên bản** trả lời câu hỏi “có thể truy cập trạng thái cũ hay không?”, còn **ghi bền dữ liệu** trả lời “trạng thái đã xác nhận có thể phục hồi sau loại sự cố nào?”. Bất biến, structural sharing, snapshot và MVCC giúp tổ chức nhiều trạng thái hoặc cách đọc nhất quán; serialization, giao thức commit, `fsync`, WAL và recovery giúp chuyển những trạng thái cần giữ sang lưu trữ bền.

Một thiết kế đúng có thể cần một trong hai hoặc **cả hai**. Hãy xác định rõ **ngữ nghĩa phiên bản**, **ranh giới xác nhận commit**, **mô hình sự cố cần chịu được** và **chính sách khôi phục/lưu trữ** trước khi lựa chọn cấu trúc dữ liệu.
