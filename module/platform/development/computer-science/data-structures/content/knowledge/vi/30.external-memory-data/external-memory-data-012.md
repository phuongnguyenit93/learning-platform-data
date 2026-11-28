# Tuần tự hóa, phiên bản định dạng và khôi phục cấu trúc từ dữ liệu lưu

## 1. Bài toán: biến cấu trúc trong RAM thành dữ liệu có thể mở lại

Giả sử dịch vụ lưu một cây tìm kiếm, bảng băm hoặc danh sách liên kết để tra cứu dữ liệu nhanh. Các cấu trúc này hoạt động dựa vào đối tượng, địa chỉ và con trỏ trong **bộ nhớ của tiến trình**. Sau khi khởi động lại, các địa chỉ cũ không còn ý nghĩa. Nếu muốn tiếp tục tra cứu mà không xử lý lại toàn bộ dữ liệu nguồn, hệ thống cần một cách **biểu diễn cấu trúc thành bytes** và **khôi phục lại bất biến của cấu trúc**.

Quá trình ấy gồm ba nhiệm vụ khác nhau:

1. **Tuần tự hóa (serialization):** chuyển trạng thái logic thành một biểu diễn lưu trữ xác định, chẳng hạn JSON, các bản ghi nhị phân hoặc trang dữ liệu.
2. **Quản lý phiên bản định dạng (format/schema versioning):** cho phép bộ đọc biết cách diễn giải dữ liệu được ghi bởi phiên bản chương trình khác, từ chối định dạng không hỗ trợ hoặc chuyển đổi bằng migration.
3. **Khôi phục (deserialization/recovery):** kiểm tra bytes và metadata, tái tạo các nút cùng liên kết, rồi chứng minh các bất biến cần thiết trước khi công bố trạng thái mới cho ứng dụng.

Trong chương **Dữ liệu ngoài bộ nhớ**, đây không chỉ là câu chuyện `json.dumps` và `json.loads`. Cách bố trí bản ghi, đọc/ghi tuần tự theo khối, chỉ số trang, kiểm tra lỗi ghi dở và cơ chế commit đều ảnh hưởng đến thời gian xử lý, bộ nhớ và tính đúng đắn.

### Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt **trạng thái logic**, **đồ thị tham chiếu trong RAM** và **bytes trên thiết bị lưu trữ**.
- Thiết kế định dạng có magic number, version, kích thước, checksum và dữ liệu payload.
- Lưu và dựng lại danh sách/cây/đồ thị bằng **ID nút** thay vì ghi địa chỉ con trỏ.
- Phân biệt **phiên bản của dữ liệu ứng dụng** với **phiên bản định dạng file**.
- Thiết kế bước đọc an toàn, migration, xác thực bất biến và quy trình xử lý file hỏng.
- Cân nhắc I/O theo khối, snapshot, log cập nhật và khôi phục sau crash.

## 2. Điều gì thực sự được lưu?

Một cấu trúc dữ liệu có thể được nhìn dưới ba lớp:

| Lớp | Ví dụ | Ý nghĩa |
|---|---|---|
| **Logic** | Tập khóa, thứ tự duyệt, các cặp khóa–giá trị | Nội dung và thao tác mà ứng dụng cần |
| **Biểu diễn trong RAM** | Các đối tượng `Node`, địa chỉ, con trỏ trái/phải, bucket, tham chiếu chia sẻ | Cách chương trình hiện tại tổ chức cấu trúc |
| **Biểu diễn trên lưu trữ** | Header, bản ghi, ID nút, offset, page ID, kiểu trường, checksum | Hợp đồng để một tiến trình khác hiểu và dựng lại |

Ví dụ danh sách liên kết `C → B → A`:

```text
Trong RAM:
  root_v2 ──► [C] ──► [B] ──► [A] ──► null
                        ▲
  root_v1 ───────────────┘

Trên thiết bị:
  roots: { "v1": 2, "v2": 3 }
  nodes:
    { id: 1, value: "A", next: null }
    { id: 2, value: "B", next: 1    }
    { id: 3, value: "C", next: 2    }
```

Các số `1,2,3` là **ID nút bên trong snapshot**, không phải địa chỉ RAM. Sau khi đọc file, ứng dụng tạo những đối tượng `Node` mới rồi kết nối theo `next_id`. Hai root cùng tham chiếu nút `2`; nếu bộ đọc dùng bảng `ID → object`, quan hệ **chia sẻ cùng một nút** được bảo toàn.

**Không tuần tự hóa địa chỉ con trỏ thô**: địa chỉ phụ thuộc tiến trình, cơ chế cấp phát bộ nhớ, hệ điều hành và nền tảng. Ghi chuỗi ký tự đại diện cho địa chỉ vào file không biến nó thành một tham chiếu hợp lệ sau khi khởi động lại.

### 2.1. Lưu giá trị hay lưu cả cấu trúc?

Cùng một tập khóa có thể được tổ chức bởi nhiều cây tìm kiếm khác nhau. Nếu chỉ cần **nội dung logic**, ta có thể tuần tự hóa các khóa theo thứ tự rồi dựng lại một cây khác khi đọc. Nếu cần giữ đúng **hình dạng cây**, thứ tự nút, các liên kết hoặc quan hệ chia sẻ giữa nhiều phiên bản, phải lưu thêm metadata về cấu trúc.

| Mục tiêu | Dữ liệu cần lưu |
|---|---|
| Khôi phục tập hợp chính xác | Danh sách phần tử và quy tắc so sánh bằng nhau |
| Khôi phục cây cân bằng với nội dung tương đương | Các khóa/giá trị; có thể dựng lại cây theo thuật toán chọn |
| Khôi phục chính xác cấu trúc cây | ID từng nút, trường dữ liệu, ID con và root |
| Khôi phục nhiều phiên bản cùng chia sẻ nút | Danh sách root theo phiên bản và bảng nút dùng chung |
| Khôi phục chỉ mục trên đĩa (B-tree/B+ tree) | Trang, khóa phân cách, child page ID, root page ID và metadata tổ chức trang |

Lưu hình dạng chính xác giúp bảo tồn một số đặc tính nội bộ, nhưng làm định dạng dễ phụ thuộc cài đặt hơn. Lưu nội dung logic đơn giản hơn cho chuyển đổi phần mềm, song cần chi phí xây dựng lại chỉ mục khi khôi phục.

## 3. Thiết kế một định dạng có thể tồn tại lâu hơn chương trình

Một file dễ bảo trì thường có **header** ở ngoài và **payload** ở trong:

```text
┌──────────┬─────────────────┬──────────────────┬───────────┬───────────┐
│ magic    │ container_ver   │ payload_length   │ checksum  │ payload   │
│ 4 byte   │ 1 byte          │ 8 byte           │ 4 byte    │ N byte    │
└──────────┴─────────────────┴──────────────────┴───────────┴───────────┘

payload JSON (minh họa):
{
  "schema_version": 2,
  "roots": { "v1": 2, "v2": 3 },
  "nodes": [
    { "id": 1, "value": "A", "next": null },
    { "id": 2, "value": "B", "next": 1 },
    { "id": 3, "value": "C", "next": 2 }
  ]
}
```

Các trường phục vụ những nhiệm vụ khác nhau:

- **Magic number** nhận diện loại file; ví dụ `DSNP` giúp phát hiện nhầm file.
- **Container version** quy định cấu trúc header, độ dài trường và cách framing bytes.
- **Payload length** cho biết bao nhiêu byte phải đọc; phải kiểm tra giới hạn trước khi cấp phát bộ nhớ.
- **Checksum** giúp phát hiện lỗi vô tình làm thay đổi bytes, ví dụ file bị cắt cụt hoặc hỏng trong quá trình ghi.
- **Schema version** quy định tên trường, kiểu dữ liệu và ý nghĩa logic của payload.

Có thể tách `container_version` và `schema_version` vì cách đóng gói ngoài cùng đôi khi giữ nguyên, còn đối tượng bên trong thay đổi. Một phần mềm có thể đọc container v1 nhưng chỉ hỗ trợ schema v1/v2, hoặc từ chối toàn bộ container v3 vì không biết cách xác định ranh giới các phần.

### 3.1. Endianness, encoding và ranh giới bản ghi

Nếu lưu số nguyên dưới dạng nhị phân, phải ghi rõ **thứ tự byte** (*endianness*), kích thước (16/32/64 bit), dấu và giới hạn giá trị. Ví dụ, số `0x01020304` dưới dạng big-endian là bytes `01 02 03 04`; một bộ đọc little-endian sẽ hiểu khác nếu không chuyển đổi.

Nếu lưu chuỗi, hãy thống nhất mã hóa như **UTF-8**, quy tắc chuẩn hóa Unicode, cách xử lý chuỗi rỗng và giới hạn chiều dài. Một cấu trúc kiểu:

```text
[độ dài bytes][bytes của chuỗi][độ dài bytes][bytes của chuỗi]...
```

khác với việc ngầm giả định “mỗi chuỗi là 10 ký tự”. Chuỗi tiếng Việt có số byte UTF-8 không nhất thiết bằng số ký tự. Với JSON, chuỗi được escape và độ dài payload phải tính trên **bytes UTF-8 đã mã hóa**, không phải số ký tự trong Python.

**Quy tắc:** định dạng lưu trữ phải độc lập với cách trình biên dịch hoặc runtime sắp xếp các trường trong struct/đối tượng. Không thể an toàn ghi trực tiếp toàn bộ vùng nhớ của một object Python xuống file rồi mong runtime khác đọc lại đúng.

## 4. Phiên bản dữ liệu và phiên bản định dạng là hai trục độc lập

Giả sử ứng dụng đã tạo các phiên bản giỏ hàng `V10, V11, V12`. Chúng là **phiên bản nội dung ứng dụng**. Trong khi đó định dạng file `schema_version: 1` hoặc `schema_version: 2` là **phiên bản quy tắc mã hóa**.

```text
               Phiên bản định dạng file
               schema v1          schema v2
Nội dung V10   có thể ghi         có thể ghi
Nội dung V11   có thể ghi         có thể ghi
Nội dung V12   có thể ghi         có thể ghi
```

Nội dung `V12` không mặc nhiên yêu cầu schema v12. Một file định dạng v2 có thể chứa hàng trăm root tương ứng hàng trăm phiên bản logic.

### 4.1. Ví dụ nâng cấp schema

Giả sử ban đầu ta lưu **một stack dưới dạng danh sách giá trị**:

```json
{
  "schema_version": 1,
  "items": ["B", "A"]
}
```

Sau đó ứng dụng cần nhiều root và muốn giữ structural sharing, nên định dạng mới lưu các nút:

```json
{
  "schema_version": 2,
  "roots": {"current": 1},
  "nodes": [
    {"id": 1, "value": "B", "next": 2},
    {"id": 2, "value": "A", "next": null}
  ]
}
```

Cả hai đều biểu diễn stack `B → A`. Nhưng schema v1 **không lưu thông tin chia sẻ đối tượng** giữa nhiều root, nên migration từ schema v1 sang v2 không thể phục hồi một lịch sử chia sẻ vốn chưa từng được ghi. Migration chỉ có thể khôi phục những thông tin mà file nguồn thực sự chứa.

### 4.2. Chiến lược tương thích

| Chiến lược | Ý nghĩa | Khi phù hợp |
|---|---|---|
| **Backward reader** | Phần mềm mới đọc được định dạng cũ | Triển khai bản mới nhưng vẫn phải mở file đã lưu nhiều năm |
| **Forward compatibility** | Phần mềm cũ hiểu một phần file mới, nếu định dạng thiết kế cho phép | Thêm trường tùy chọn có quy tắc mặc định và cơ chế bỏ qua an toàn |
| **Migration khi đọc** | Chuyển schema cũ sang mô hình nội bộ hiện tại | Số định dạng cũ không nhiều, chi phí chấp nhận được |
| **Migration ngoại tuyến** | Chuyển hàng loạt file bằng công cụ riêng | Thay đổi lớn, cần theo dõi tiến độ và kế hoạch khôi phục |
| **Từ chối có kiểm soát** | Báo lỗi rõ ràng khi gặp phiên bản không biết | Khi không thể diễn giải chính xác mà không làm sai dữ liệu |

Không được mặc định rằng “field không biết thì bỏ qua” luôn an toàn. Một trường mới có thể thay đổi ý nghĩa của khóa, thứ tự so sánh hoặc đơn vị tính. **Quy tắc bỏ qua trường** phải là một phần của hợp đồng định dạng.

## 5. Khôi phục cấu trúc có tham chiếu: hai pha và kiểm tra bất biến

Nếu chỉ tuần tự hóa các cặp khóa–giá trị không liên kết, đọc JSON vào `dict` có vẻ đơn giản. Với danh sách liên kết, cây hoặc đồ thị, cấu trúc có **tham chiếu**:

```text
serialized_node:
  id:    7
  value: "X"
  next:  11
```

Một trình khôi phục đáng tin cậy phải làm nhiều hơn việc tạo các object:

1. **Đọc và xác thực container:** đúng magic/version, không vượt giới hạn kích thước, số bytes đúng, checksum hợp lệ.
2. **Xác định schema:** hỗ trợ trực tiếp hoặc chuyển đổi schema cũ sang schema nội bộ đã biết.
3. **Tạo bảng ID:** phát hiện ID trùng, thiếu trường, sai kiểu, tham chiếu tới ID không tồn tại.
4. **Lắp liên kết:** ánh xạ ID vào object, không tái tạo độc lập một node mỗi lần tham chiếu tới ID đó.
5. **Kiểm tra bất biến:** danh sách không có chu trình ngoài ý muốn; cây tìm kiếm tuân thứ tự khóa; B-tree/B+ tree có khóa phân cách và con trỏ hợp lệ.
6. **Công bố kết quả:** chỉ cho ứng dụng dùng root đã khôi phục sau khi mọi kiểm tra cần thiết thành công.

Đối với đồ thị có chu trình hợp lệ, trình đọc phải hỗ trợ chu trình bằng cơ chế tạo object trước rồi nối cạnh sau. Đối với danh sách liên kết đơn không được có chu trình, gặp chu trình phải **báo dữ liệu lỗi** thay vì cố tạo một danh sách vô hạn.

### 5.1. Bất biến cần xác thực tùy cấu trúc

| Cấu trúc | Kiểm tra sau khi đọc |
|---|---|
| Mảng | Độ dài khai báo, kiểu từng phần tử, offset nằm trong vùng file |
| Danh sách liên kết | Root hợp lệ, `next_id` tồn tại, không có chu trình nếu danh sách tuyến tính |
| Cây tìm kiếm nhị phân | Mỗi node có con hợp lệ, không có chu trình, quy tắc `left < key < right` hoặc quy ước khóa trùng |
| Heap | Quan hệ cha–con thỏa heap property; chỉ số con nằm trong giới hạn |
| B-tree/B+ tree | Số khóa và số con hợp lệ; thứ tự khóa, độ sâu lá, miền khóa, root page, linked leaves phù hợp |
| Bảng băm | Hash/seed, số bucket, cách xử lý va chạm; dựng lại hoặc rehash khi cấu hình thay đổi |
| Đồ thị | ID đỉnh/cạnh hợp lệ, trọng số/kiểu cạnh, hướng, nhãn, tham chiếu và chu trình theo quy tắc ứng dụng |

Không nên coi việc `json.loads` hoặc giải mã nhị phân thành công là bằng chứng “cấu trúc đã khôi phục đúng”. File có thể hợp lệ về cú pháp nhưng chứa một root không tồn tại, hai node trùng ID hoặc khóa của cây bị đặt sai nhánh.

## 6. Ví dụ Python tự chứa: lưu và phục hồi stack có chia sẻ nút

Ví dụ dưới đây lưu nhiều phiên bản của **stack bất biến** dùng danh sách liên kết. Tập trung vào những nguyên tắc quan trọng:

- Gán một **ID duy nhất cho mỗi đối tượng node** trong snapshot, giữ được các đuôi dùng chung.
- Ghi header nhị phân với `magic`, `container_version`, kích thước payload và CRC32, dùng thứ tự byte **big-endian**.
- Ghi JSON có `schema_version: 2`, đọc cả schema v1 cũ và chuyển đổi lên mô hình v2.
- Giới hạn dung lượng và số nút, phát hiện ID trùng, tham chiếu thiếu, chu trình và bản ghi không tới được root.
- Khi lưu, dùng tệp tạm trong cùng thư mục, đồng bộ tệp rồi thay tên; một số hệ thống POSIX còn cần đồng bộ thư mục.

**Đây là mẫu học tập**, không phải thư viện lưu trữ giao dịch đã được kiểm chứng trên mọi nền tảng.

```python
from __future__ import annotations

import json
import os
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"DSNP"
CONTAINER_VERSION = 1
HEADER = struct.Struct(">4sBQI")  # magic, version, length, crc32
MAX_PAYLOAD = 8 * 1024 * 1024
MAX_NODES = 100_000


@dataclass(frozen=True)
class Node:
    value: str
    next: Node | None = None


def to_document(versions: dict[str, Node | None]) -> dict:
    """Tao schema v2, giu chia se object theo danh tinh node."""
    ids = {}       # id(object) -> id on disk
    records = {}   # id on disk -> record
    pending = []

    def node_id(node):
        if node is None:
            return None
        if not isinstance(node, Node):
            raise ValueError("next khong phai Node")
        identity = id(node)
        if identity in ids:
            return ids[identity]
        if len(ids) >= MAX_NODES:
            raise ValueError("qua nhieu node")
        new_id = len(ids) + 1
        ids[identity] = new_id
        record = {"id": new_id, "value": node.value, "next": None}
        records[new_id] = record
        pending.append((node, record))
        return new_id

    roots = {}
    for name, head in versions.items():
        if not isinstance(name, str) or not name:
            raise ValueError("ten phien ban khong hop le")
        roots[name] = node_id(head)

    while pending:
        node, record = pending.pop()
        if not isinstance(node.value, str):
            raise ValueError("gia tri node phai la string")
        record["next"] = node_id(node.next)

    return {
        "schema_version": 2,
        "roots": roots,
        "nodes": list(records.values())
    }


def normalize_document(document: dict) -> dict:
    """Chuyen v1 -> v2; khong doan y nghia schema moi."""
    if not isinstance(document, dict):
        raise ValueError("payload phai la object")
    version = document.get("schema_version")
    if type(version) is not int:
        raise ValueError("schema_version khong hop le")
    if version == 2:
        if set(document) != {"schema_version", "roots", "nodes"}:
            raise ValueError("schema v2 thieu/du field")
        return document
    if version != 1:
        raise ValueError("schema_version khong duoc ho tro")

    if set(document) != {"schema_version", "items"}:
        raise ValueError("schema v1 thieu/du field")
    items = document.get("items")
    if not isinstance(items, list) or len(items) > MAX_NODES:
        raise ValueError("v1 items khong hop le")
    if any(not isinstance(value, str) for value in items):
        raise ValueError("v1 chi ho tro string")
    nodes = [
        {
            "id": i + 1,
            "value": value,
            "next": i + 2 if i + 1 < len(items) else None
        }
        for i, value in enumerate(items)
    ]
    return {
        "schema_version": 2,
        "roots": {"current": 1 if nodes else None},
        "nodes": nodes
    }


def from_document(source: dict) -> dict[str, Node | None]:
    document = normalize_document(source)
    records = document.get("nodes")
    roots = document.get("roots")
    if not isinstance(records, list) or len(records) > MAX_NODES:
        raise ValueError("danh sach node khong hop le")
    if not isinstance(roots, dict):
        raise ValueError("roots khong hop le")

    raw = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("node record phai la object")
        if set(record) != {"id", "value", "next"}:
            raise ValueError("thieu/du field trong node")
        ident = record["id"]
        value = record["value"]
        nxt = record["next"]
        if type(ident) is not int or ident <= 0 or ident in raw:
            raise ValueError("node id trung hoac khong hop le")
        if not isinstance(value, str):
            raise ValueError("node value phai la string")
        if nxt is not None and (type(nxt) is not int or nxt <= 0):
            raise ValueError("next id khong hop le")
        raw[ident] = (value, nxt)

    for _, nxt in raw.values():
        if nxt is not None and nxt not in raw:
            raise ValueError("tham chieu toi node khong ton tai")
    for name, root in roots.items():
        if not isinstance(name, str) or not name:
            raise ValueError("ten phien ban khong hop le")
        if root is not None and (
            type(root) is not int or root not in raw
        ):
            raise ValueError("root id khong ton tai")

    built = {}
    state = {}  # 1: dang duyet, 2: da lap xong
    for root in roots.values():
        cursor = root
        chain = []
        while cursor is not None and state.get(cursor) != 2:
            if state.get(cursor) == 1:
                raise ValueError("phat hien chu trinh")
            state[cursor] = 1
            chain.append(cursor)
            cursor = raw[cursor][1]
        while chain:
            ident = chain.pop()
            value, nxt = raw[ident]
            built[ident] = Node(value, built.get(nxt))
            state[ident] = 2

    if len(built) != len(raw):
        raise ValueError("co node khong the den tu root")
    return {
        name: (built[root] if root is not None else None)
        for name, root in roots.items()
    }


def save(path: str, versions: dict[str, Node | None]) -> None:
    payload = json.dumps(
        to_document(versions),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload qua lon")

    header = HEADER.pack(
        MAGIC, CONTAINER_VERSION, len(payload),
        zlib.crc32(payload)
    )
    target = Path(path)
    fd, temp = tempfile.mkstemp(
        prefix="." + target.name + ".",
        suffix=".tmp",
        dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(header)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)

        # POSIX: yeu cau sync thu muc neu he thong cho phep.
        if os.name == "posix":
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def load(path: str) -> dict[str, Node | None]:
    with open(path, "rb") as stream:
        raw_header = stream.read(HEADER.size)
        if len(raw_header) != HEADER.size:
            raise ValueError("header bi cat")
        magic, version, length, expected_crc = HEADER.unpack(raw_header)
        if magic != MAGIC or version != CONTAINER_VERSION:
            raise ValueError("container khong duoc ho tro")
        if length > MAX_PAYLOAD:
            raise ValueError("payload length qua gioi han")
        payload = stream.read(length)
        if len(payload) != length or stream.read(1):
            raise ValueError("file cat cut hoac du byte")
    if zlib.crc32(payload) != expected_crc:
        raise ValueError("CRC32 khong khop")
    return from_document(json.loads(payload.decode("utf-8")))


# Hai phien ban chia se cung duoi ["B", "A"].
v1 = Node("A")
v2 = Node("B", v1)
v3 = Node("C", v2)
save("example.dsnp", {"v2": v2, "v3": v3})

restored = load("example.dsnp")
assert restored["v3"].next is restored["v2"]
assert restored["v2"].next.value == "A"
```

### 6.1. Những bảo đảm và giới hạn của ví dụ

Đoạn mã dùng `id(object)` **chỉ trong quá trình tuần tự hóa** để nhận ra khi hai root cùng tham chiếu một node, rồi chuyển sang ID ổn định trong file. File không chứa giá trị `id(object)` của Python. Khi dựng lại, cùng một ID trên đĩa ánh xạ tới cùng một object, vì vậy `restored["v3"].next is restored["v2"]` có thể đúng.

Hàm `from_document` kiểm tra chu trình ở danh sách, không cho node mồ côi và dùng quá trình lắp từ đuôi lên đầu để tránh đệ quy sâu. Khi đọc schema v1, quá trình migration dựng nội dung tương đương, nhưng không thể tạo lại quan hệ chia sẻ giữa các phiên bản chưa được v1 mô tả.

**Quan trọng:** mặc dù dùng tệp tạm, `fsync` và `os.replace`, đây chưa phải một giao thức giao dịch hoàn chỉnh: chưa xử lý hai tiến trình ghi đồng thời, nhiều file phải commit cùng nhau, khả năng lỗi thiết bị, backup hay sửa chữa dữ liệu sau khi hỏng. Bảo đảm của `os.replace` và đồng bộ thư mục phụ thuộc OS, file system, thiết bị và cấu hình. Trên Windows hoặc môi trường không hỗ trợ sync thư mục theo cách trên, cần chọn API/hợp đồng lưu bền tương ứng. Không nên lấy mẫu minh họa làm cam kết chống mất dữ liệu trong mọi môi trường.

CRC32 giúp phát hiện hỏng dữ liệu **vô tình**, không chống sửa đổi ác ý. Nếu dữ liệu nhận từ nguồn không tin cậy, cần thêm xác thực nguồn, chữ ký/MAC khi phù hợp, giới hạn tài nguyên và chính sách phân quyền. Không dùng `pickle.loads` cho dữ liệu không tin cậy vì định dạng pickle có thể thực thi mã khi giải tuần tự.

## 7. Khôi phục index trên đĩa: page ID khác object ID

Với B-tree hoặc B+ tree dùng cho dữ liệu ngoài RAM, các node thường được lưu trong **trang cố định** (ví dụ 4 KiB hoặc 16 KiB) và mỗi trang có `page_id`. Một bố cục đơn giản:

```text
File header:
  magic, format_version, page_size, root_page_id,
  generation, checksum, free_page_head ...

Page:
  page_id, page_type, key_count, checksum, ...
  sorted_keys[]
  payload[] hoặc child_page_ids[]
```

Con trỏ trong RAM `node.left` được thay bởi `child_page_id` trên đĩa. Khi truy vấn, buffer manager tìm trang đã cache hoặc đọc trang tương ứng. Việc khôi phục có thể chỉ cần nạp header và root trước; các trang khác được tải **theo yêu cầu** thay vì đọc toàn bộ cây vào RAM.

### 7.1. Bất biến quan trọng của B+ tree khi khôi phục

- `root_page_id` tồn tại, trỏ tới loại trang hợp lệ.
- Các khóa trong mỗi node được sắp xếp đúng theo **comparator** đã định nghĩa; phải version hóa cả quy tắc so sánh/collation khi nó ảnh hưởng đến thứ tự.
- Số child pointer phù hợp số khóa phân cách; page ID không trỏ ra ngoài file hoặc vào trang đang đánh dấu rỗng.
- Các ràng buộc về số khóa tối thiểu/tối đa và độ sâu lá tuân biến thể B-tree/B+ tree đang dùng.
- Với B+ tree, các liên kết giữa lá (nếu dùng để duyệt range) phải nhất quán hoặc được kiểm tra/sửa chữa theo quy trình rõ ràng.

Một trang có checksum đúng vẫn có thể vi phạm thứ tự khóa hoặc trỏ nhầm trang. Vì vậy, **kiểm tra toàn vẹn bytes** và **kiểm tra bất biến logic** là hai bước khác nhau.

### 7.2. Không nhất thiết nạp mọi node

Trong mô hình external memory, giả sử một block/trang chứa `B` bản ghi và tập dữ liệu có `N` bản ghi. Duyệt tuần tự để xây lại chỉ mục có thể đạt số lần đọc cỡ `O(N/B)` block (bỏ qua chi tiết trang đầu/cuối), trong khi đọc từng bản ghi bằng I/O ngẫu nhiên có thể tiến gần `O(N)` lượt truy cập, đắt hơn nhiều.

Khi ghi một snapshot lớn, nên nhóm các bản ghi liên tục và dùng I/O theo khối; khi khôi phục, có thể đọc tuần tự hoặc thực hiện **bulk load** để dựng cây cân bằng. Một định dạng nhị phân có page ID và offset giúp truy cập ngẫu nhiên nhanh, nhưng yêu cầu quản lý fragmentation, free list và version layout nghiêm ngặt hơn JSON.

## 8. Durability: ghi file hợp lệ khác với commit bền

Giả sử ứng dụng đã tạo trạng thái `V12` trong RAM. Quá trình có thể thất bại ở những mốc khác nhau:

| Thời điểm lỗi | Khả năng gặp phải | Cách phòng vệ |
|---|---|---|
| Trước khi serialize xong | Payload chưa hoàn chỉnh | Không thay thế snapshot đang dùng |
| Đang ghi tệp tạm | Tệp mới bị cắt cụt | Header length/checksum phát hiện; giữ snapshot cũ |
| Sau ghi nhưng chưa sync bắt buộc | Bytes có thể chỉ nằm trong cache | Không xác nhận commit bền quá sớm |
| Sau thay tên nhưng chưa sync thư mục khi cần | Tên mới có thể chưa bền | Tuân thủ giao thức đồng bộ của nền tảng |
| Sau commit bền | Snapshot mới phải khôi phục được theo hợp đồng | Kiểm tra checksum và metadata khi khởi động |

Một quy trình snapshot an toàn cho **một file** thường là ghi vào tệp tạm cùng filesystem, đồng bộ nội dung, thay tên nguyên tử và đồng bộ metadata cần thiết. Cần nói rõ bảo đảm của nền tảng; không được đánh đồng “`write` trả về thành công” với “sống sót sau mất điện”.

### 8.1. Snapshot + Write-Ahead Log

Nếu snapshot chứa hàng triệu bản ghi, việc serialize toàn bộ sau mỗi cập nhật thường quá tốn I/O. Một thiết kế khác kết hợp:

```text
checkpoint/snapshot hợp lệ tại phiên bản 100
       |
       v
WAL: thay đổi 101 (đã commit)
WAL: thay đổi 102 (đã commit)
WAL: thay đổi 103 (chưa commit, bị dở)
       |
       v
Restart:
  đọc checkpoint 100
  kiểm tra log -> replay 101, 102
  bỏ qua/xử lý 103 theo giao thức recovery
       |
       v
trạng thái phục hồi tại phiên bản 102
```

WAL cần một định dạng có ranh giới bản ghi, transaction ID, commit marker/LSN, kiểm tra lỗi cắt cụt và quy tắc replay idempotent hoặc xử lý lặp. Ghi journal trước khi dữ liệu phụ thuộc được công bố bền là cốt lõi, nhưng **chỉ có file WAL không tự bảo đảm đúng** nếu thứ tự sync, transaction hoặc recovery sai.

Đối với hệ thống cần nhiều phiên bản truy vấn lại, bản ghi WAL dùng cho crash recovery chưa chắc đủ: log có thể được dọn sau checkpoint. Phải thiết kế chính sách giữ lịch sử độc lập với chính sách bảo đảm phục hồi phiên bản **đã commit mới nhất**.

## 9. Xử lý schema evolution và triển khai cuốn chiếu

Khi nâng cấp dịch vụ nhiều máy, một số máy có thể ghi schema mới trong khi máy khác vẫn chạy phần mềm cũ. Nếu máy cũ không hiểu dữ liệu mới, hệ thống phải có chiến lược:

1. **Đọc trước, ghi sau:** triển khai bộ đọc hỗ trợ schema mới trên tất cả các máy, nhưng vẫn ghi schema cũ một thời gian.
2. **Thử migration:** mở file schema cũ trên phần mềm mới, chuyển đổi và kiểm tra kết quả cùng bộ dữ liệu chuẩn.
3. **Bật ghi định dạng mới:** chỉ khi tất cả bên đọc yêu cầu đã hiểu.
4. **Giữ rollback có giới hạn:** nếu cần hạ cấp phần mềm, xác định phiên bản định dạng nào còn đọc được; không hứa rollback khi file đã dùng trường mới không thể chuyển ngược.
5. **Ngừng hỗ trợ schema cũ có thông báo:** chỉ khi dữ liệu còn tồn tại đã được migration hoặc có quy trình khôi phục rõ ràng.

Nếu thay đổi các thuộc tính như `hash(seed)` của bảng băm, comparator của cây, mã hóa khóa, cách xử lý khóa trùng hoặc page size, việc “đọc field đúng kiểu” **không đủ**. Có thể phải **xây lại chỉ mục** từ các bản ghi logic, vì trạng thái cũ và mới dùng bất biến khác nhau.

### 9.1. Version hóa cái gì?

Ngoài `schema_version` của payload, hệ thống có thể cần metadata cho:

- **Algorithm version:** cách băm, comparator, cân bằng cây hoặc giải mã trang.
- **Encoding version:** UTF-8 và chính sách chuẩn hóa chuỗi.
- **Compression version:** thuật toán và từ điển nén nếu có.
- **Encryption/key ID:** định danh khóa mã hóa, nonce và cơ chế xác thực (không để lộ khóa bí mật).
- **Page format/version:** header trang, kích thước trang, alignment, endianness.
- **Feature flags:** có hay không các trường hoặc cấu trúc mở rộng với quy tắc tương thích rõ ràng.

Không nên phụ thuộc vào việc tên file có đuôi `.v2` để giải mã: header nội tại vẫn cần đủ thông tin nhận diện nội dung. Nếu file có thể bị thay tên, truyền qua mạng hoặc di chuyển sang máy khác, metadata nhúng trong file giúp phát hiện định dạng sai.

## 10. Kiểm thử round-trip, migration và tình huống lỗi

Một triển khai lưu/đọc chỉ nên được coi là sẵn sàng sau khi kiểm tra tối thiểu những nhóm sau:

| Nhóm kiểm thử | Điều cần xác nhận |
|---|---|
| **Round-trip** | `decode(encode(x))` tương đương `x` theo ngữ nghĩa cần bảo toàn |
| **Structural sharing** | Hai root cùng tham chiếu một ID khôi phục thành **cùng object** nếu đó là hợp đồng |
| **Rỗng và biên** | Không có phần tử, một phần tử, nhiều phần tử, chuỗi Unicode, kích thước tối đa |
| **Phiên bản** | File cũ đọc được qua migration; version lạ bị từ chối rõ ràng |
| **Corruption** | Header thiếu, length sai, checksum sai, file thừa bytes, ID trùng, tham chiếu thiếu |
| **Bất biến** | Không có chu trình ở danh sách; BST/B+ tree giữ thứ tự và quan hệ trang |
| **Giới hạn tài nguyên** | Length cực lớn, nhiều node, tham chiếu sâu hoặc dữ liệu cố tình gây quá tải bị từ chối an toàn |
| **Crash/recovery** | Lỗi ở trước/sau bước ghi và commit không làm công bố snapshot dở dang |
| **Đa phiên bản phần mềm** | File tạo bởi phiên bản được hỗ trợ vẫn mở được trên các phiên bản đọc tương ứng |

Đừng chỉ so sánh `str(x)` trước và sau khi đọc. Ví dụ hai cây có thứ tự duyệt bằng nhau nhưng một cây bị mất quy tắc cân bằng; nếu ứng dụng đòi độ sâu `O(log n)` thì chúng chưa tương đương về mặt cấu trúc và hiệu năng.

### 10.1. Nguyên tắc khôi phục thất bại an toàn

Nếu gặp file không hợp lệ, hệ thống không nên lặng lẽ sửa dữ liệu rồi ghi đè lên bản gốc. Có thể:

- Giữ nguyên file lỗi để điều tra, ghi nhận reason code nhưng không phát tán thông tin nhạy cảm.
- Thử checkpoint/snapshot hợp lệ trước đó hoặc bản backup đáng tin cậy.
- Dùng WAL đã xác thực để replay giao dịch hoàn chỉnh theo đúng thứ tự.
- Xây lại index từ nguồn dữ liệu logic nếu index chỉ là dữ liệu dẫn xuất.
- Báo lỗi có thể xử lý thay vì trả về cấu trúc nửa khôi phục với những bất biến bị phá vỡ.

**Khôi phục index** từ dữ liệu nguồn và **khôi phục dữ liệu gốc** là hai vấn đề khác nhau. Một chỉ mục B+ tree bị hỏng có thể được xây lại khi vẫn còn các bản ghi nguồn bền, nhưng nếu dữ liệu gốc chỉ tồn tại trong những trang hỏng, cần kế hoạch backup/recovery mạnh hơn.

## 11. Chọn chiến lược theo quy mô và yêu cầu

| Tình huống | Chiến lược phù hợp | Đánh đổi |
|---|---|---|
| File cấu hình nhỏ, ít cập nhật | JSON hoặc định dạng rõ ràng + snapshot nguyên tệp | Dễ debug, nhưng mỗi lần ghi có thể cần ghi toàn bộ |
| Cây/đồ thị nhỏ cần giữ hình dạng | Node ID + root ID + checksum | Phục hồi được liên kết; phải kiểm tra chu trình/tham chiếu |
| Dữ liệu lớn chủ yếu đọc tuần tự | Bản ghi liên tục + length prefix, bulk load index | I/O tuần tự tốt; truy cập ngẫu nhiên cần index riêng |
| Chỉ mục lớn lưu trực tiếp trên đĩa | Page ID, page header, B-tree/B+ tree + buffer manager | Truy cập theo trang hiệu quả; versioning và recovery phức tạp |
| Cập nhật nhỏ nhưng thường xuyên | Snapshot định kỳ + WAL/checkpoint | Ghi ít hơn mỗi lần; khôi phục phải replay log |
| Nhiều bản dữ liệu lịch sử | Multi-root snapshots hoặc MVCC + retention | Có time travel; cần thu gom phiên bản cũ |
| Dữ liệu nhạy cảm/không tin cậy | Format giới hạn rõ, xác thực, kiểm tra schema và tài nguyên | Chi phí kiểm tra và quản lý khóa/metadata tăng |

Hãy bắt đầu từ **thứ phải khôi phục**: chỉ nội dung logic, thứ tự, hình dạng cây, cấu trúc chia sẻ hay lịch sử nhiều phiên bản. Từ đó mới chọn dữ liệu nào cần lưu và bao nhiêu chi phí I/O được chấp nhận.

## 12. Bài tập tự kiểm tra

**Câu 1.** Một file chứa các chuỗi `"A", "B", "C"` nhưng không chứa con trỏ. Có thể khôi phục **chính xác hình dạng** của cây tìm kiếm trước khi lưu không?

**Đáp án:** Không nhất thiết. Có thể dựng một cây có cùng nội dung logic nếu biết comparator và quy ước khóa trùng, nhưng hình dạng cũ phụ thuộc cấu trúc/link hoặc lịch sử chèn mà file không lưu.

**Câu 2.** Hai phiên bản danh sách chia sẻ nút `N7` trong RAM. Khi tuần tự hóa, mỗi lần thấy `N7` đều tạo một bản ghi node mới. Điều gì bị mất?

**Đáp án:** Quan hệ **cùng một node** (structural sharing). Cần ánh xạ danh tính object sang một node ID duy nhất trong file, rồi dùng chung object khi khôi phục.

**Câu 3.** File có `schema_version: 5` nhưng bộ đọc chỉ hỗ trợ v1/v2. Có nên tự thử parse như v2 không?

**Đáp án:** Không. Cần từ chối có kiểm soát hoặc dùng bộ migration được định nghĩa rõ. Đoán định dạng có thể diễn giải sai trường và phá bất biến.

**Câu 4.** Một snapshot có checksum CRC32 khớp nhưng trường `root_page_id` trỏ tới trang không tồn tại. File có hợp lệ để công bố không?

**Đáp án:** Không. CRC32 chỉ kiểm tra bytes theo checksum, không chứng minh **bất biến logic**. Phải xác thực ID/trang và cấu trúc trước khi công bố.

**Câu 5.** Vì sao cần giới hạn `payload_length` **trước** khi gọi đọc/cấp phát bộ nhớ?

**Đáp án:** Trường length trong file có thể bị lỗi hoặc do tác nhân xấu đặt cực lớn, khiến chương trình cấp phát quá nhiều RAM hoặc bị từ chối dịch vụ.

**Câu 6.** Ứng dụng dùng `write()` để thay file snapshot, sau đó trả thành công nhưng chưa sync theo hợp đồng lưu trữ. Có thể bảo đảm snapshot mới còn sau mất điện không?

**Đáp án:** Không. Bytes có thể vẫn ở bộ đệm; phải tuân thủ giao thức đồng bộ và commit phù hợp OS/file system.

**Câu 7.** Với `N = 1.000.000` bản ghi và `B = 100` bản ghi trong mỗi block, đọc tuần tự tối thiểu khoảng bao nhiêu block (bỏ qua metadata)?

**Đáp án:** Khoảng `N/B = 10.000` block, cho thấy lý do sắp xếp bản ghi liên tục giúp tối ưu I/O khi dựng lại index.

**Câu 8.** Cơ sở dữ liệu có checkpoint đến giao dịch 100 và WAL chứa giao dịch 101, 102 đã commit, giao dịch 103 chưa commit. Sau crash nên phục hồi đến đâu?

**Đáp án:** Dựng trạng thái từ checkpoint 100 và replay các giao dịch hợp lệ **đã commit** 101, 102; xử lý/bỏ qua giao dịch 103 theo quy tắc recovery, không tự công bố nó là thành công.

**Câu 9.** Khi đổi comparator của B+ tree, có luôn đủ nếu thay một trường `comparator_version` trong header mà không đụng dữ liệu trang?

**Đáp án:** Không. Nếu thứ tự khóa thay đổi, các khóa phân cách/trang cũ có thể không còn tuân bất biến. Cần một migration hoặc xây lại index phù hợp.

**Câu 10.** Một file định dạng cũ chỉ chứa dữ liệu stack mới nhất. Phần mềm mới muốn đọc lại mười phiên bản trước. Migration có thể tự tạo ra lịch sử thật không?

**Đáp án:** Không. Migration chỉ chuyển đổi thông tin đã lưu; không thể suy ra các phiên bản cũ đã bị mất nếu file không chứa lịch sử hoặc log đủ để tái dựng.

## Kết luận

**Tuần tự hóa** quyết định cách biến cấu trúc thành dữ liệu có thể lưu, **phiên bản định dạng** quyết định bộ đọc có thể hiểu dữ liệu theo hợp đồng nào, còn **khôi phục** phải dựng lại liên kết và kiểm tra bất biến trước khi trả quyền sử dụng cho ứng dụng. Với dữ liệu ngoài RAM, thêm các yêu cầu về block I/O, page ID, snapshot/WAL, kiểm tra lỗi và commit bền.

Một hệ thống thiết kế tốt không chỉ trả lời “ghi file thành công chưa?”, mà còn trả lời được: **file thuộc định dạng nào, khôi phục được những gì, loại lỗi nào được phát hiện, trường hợp nào được tự động phục hồi và khi nào trạng thái đã đủ tin cậy để công bố**.
