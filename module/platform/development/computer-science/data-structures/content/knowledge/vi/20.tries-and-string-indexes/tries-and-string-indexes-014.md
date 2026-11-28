# Quy ước chuẩn hóa Unicode và so sánh khóa chuỗi khi lập chỉ mục

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Quy ước chuẩn hóa Unicode và so sánh khóa chuỗi khi lập chỉ mục

Một hệ thống lưu tên `"Café"` nhưng nhận truy vấn `"Cafe\u0301"` (chữ `e` rồi dấu sắc kết hợp). Hai chuỗi có thể hiển thị giống nhau, dù **không có cùng dãy mã Unicode**. Nếu lưu trực tiếp vào trie, bảng băm, cây tìm kiếm ba nhánh hoặc mảng hậu tố, chúng có thể đi theo những đường tìm khác nhau. Mặt khác, tìm `"STRASSE"` có nên khớp `"Straße"`? Tra tiền tố `"ca"` có nên thấy `"cá"`? Sắp `"ă"` trước hay sau `"z"`?

Không câu hỏi nào được giải quyết hoàn toàn bằng một dòng “chuyển hết về chữ thường”. **Quan hệ bằng nhau, thứ tự khóa, ngữ nghĩa tiền tố, cách ánh xạ vị trí và chính sách hiển thị là những phần riêng của đặc tả chỉ mục.**

Bài học thuộc chương **Trie và chỉ mục chuỗi** của mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`. Theo mục tiêu mô-đun xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta sẽ học qua **bất biến**, thao tác, độ phức tạp thời gian–bộ nhớ và lựa chọn cấu trúc theo bài toán. Ví dụ dùng Python `unicodedata`, nhưng tư tưởng áp dụng rộng hơn cho Java, JavaScript, C++, database và hệ thống tìm kiếm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **byte**, **Unicode code point**, **UTF-16 code unit** và **grapheme cluster**.
2. Giải thích **canonical equivalence**, **compatibility equivalence** và bốn chuẩn `NFC`, `NFD`, `NFKC`, `NFKD`.
3. Phân biệt **casefold** với `lower`, **bỏ dấu** với chuẩn hóa và **collation** với thứ tự code point.
4. Thiết kế hàm sinh **normalized key** xác định, dùng nhất quán ở mọi thao tác chỉ mục.
5. Bảo toàn các bản ghi nguồn có **cùng khóa đã chuẩn hóa** bằng posting list.
6. Giải thích ý nghĩa của **prefix search trên normalized key**, gồm những khác biệt với prefix của chuỗi nguồn.
7. Dùng cùng quan hệ so sánh khi xây và tìm trên Hash Map, Trie, TST hoặc mảng đã sắp.
8. Hiểu vì sao chuẩn hóa toàn bộ văn bản có thể làm **offset kết quả substring** khác offset nguồn.
9. Cài đặt một chỉ mục khóa chuỗi tĩnh hỗ trợ `exact` và `prefix` bằng Python.
10. Phân tích chi phí chuẩn hóa, sort, binary search, posting list và xuất kết quả.
11. Đặt ra quy định về locale, phiên bản Unicode, an toàn identifier và nâng phiên bản chỉ mục.
12. Xây bộ kiểm thử độc lập cho equivalence, thứ tự, prefix, collision và trường hợp Unicode biên.

## 2. Phải định nghĩa rõ bốn loại truy vấn

Một ứng dụng xử lý chuỗi có thể hỏi:

| Câu hỏi | Quan hệ cần quy định | Ví dụ |
| --- | --- | --- |
| Hai khóa có là một không? | **Equality** | `"é"` so với `"e\u0301"` |
| Khóa nào đứng trước? | **Ordering** | `"ă"` so với `"z"` |
| Khóa nào bắt đầu bằng mẫu? | **Prefix** | `"ca"` so với `"cá"` |
| Mẫu nằm ở vị trí nào? | **Substring và offset** | `"é"` trong `"cafe\u0301"` |

Các quan hệ này **không buộc phải giống nhau**. Hệ thống có thể dùng equality theo NFC, tìm kiếm không phân biệt chữ hoa/thường, hiển thị theo thứ tự từ điển tiếng Việt và giữ nguyên chuỗi nguồn để tô sáng.

### 2.1. Ba dạng lưu trữ cho cùng một bản ghi

```text
source_text:    "Cafe\u0301"   # Chuỗi gốc
canonical_key:  "Café"        # Khóa so bằng canonical
search_key:     "café"        # Khóa tìm qua NFC + casefold
```

Không nên ghi đè `source_text` bằng `search_key` nếu cần bảo toàn cách viết gốc. Một bản ghi có thể cần **nhiều chỉ mục** phục vụ các hợp đồng khác nhau.

### 2.2. Khóa nguồn không nhất thiết là định danh

Hai bản ghi tên `Café` có thể là hai thực thể khác nhau. Cùng normalized key không có nghĩa chúng là cùng một bản ghi. Nên tách **record ID** khỏi **search key**.

## 3. Unicode: code point không đồng nghĩa với ký tự hiển thị

Unicode gán cho một code point mã như `U+0065` (chữ `e`) hay `U+0301` (dấu sắc kết hợp). Encoding như UTF-8/UTF-16 biến dãy code point thành byte hoặc code unit.

### 3.1. Một chữ, hai dãy code point

```text
Dạng dựng sẵn:     U+00E9          ("é")
Dạng tách dấu:     U+0065 U+0301   ("e" + dấu sắc)
```

Python so `str` theo code point:

```python
a = "\u00e9"
b = "e\u0301"

assert a != b
assert len(a) == 1
assert len(b) == 2
assert len(a.encode("utf-8")) == 2
assert len(b.encode("utf-8")) == 3
```

### 3.2. Code point, byte và grapheme

- `len(str)` của Python đếm **code point**.
- `len(bytes)` đếm **byte**.
- Một **grapheme cluster** là đơn vị mà người dùng thường nhận là một ký tự; nó có thể gồm nhiều code point.

Emoji ghép bằng `ZWJ`, dấu kết hợp, regional indicator và variation selector có thể khiến độ dài theo ba đơn vị khác nhau.

### 3.3. Khác biệt giữa ngôn ngữ lập trình

Java và JavaScript có nhiều API đánh chỉ số chuỗi theo **UTF-16 code unit**, không giống chỉ số code point của Python `str`. Một ký tự ngoài BMP có thể chiếm **hai** code unit UTF-16.

**Bất biến bắt buộc:** các API trả vị trí phải nêu rõ **byte offset, code point offset, UTF-16 offset hay grapheme offset**.

## 4. Canonical equivalence: NFC và NFD

Unicode có quan hệ **tương đương canonical** giữa những cách biểu diễn khác nhau của cùng ký tự.

- `NFD`: phân rã canonical và sắp thứ tự dấu kết hợp phù hợp.
- `NFC`: phân rã canonical rồi tổ hợp canonical khi có thể.

```python
import unicodedata as ud

a = "\u00e9"
b = "e\u0301"

assert ud.normalize("NFC", a) == ud.normalize("NFC", b)
assert ud.normalize("NFD", a) == ud.normalize("NFD", b)

assert ud.normalize("NFC", b) == "\u00e9"
assert ud.normalize("NFD", a) == "e\u0301"
```

### 4.1. NFC không có nghĩa bỏ dấu

`"a"` và `"á"` vẫn khác nhau sau NFC. Tương tự, chuẩn hóa NFC không chuyển tất cả chữ thành chữ thường.

Chuẩn hóa canonical chỉ làm tương đương các dãy code point theo **quy tắc canonical** của Unicode.

### 4.2. NFC không luôn làm một chữ thành một code point

Một số tổ hợp dấu không có dạng dựng sẵn. Kết quả NFC có thể vẫn là nhiều code point; không được xem `len(NFC(s))` là số grapheme hoặc số chữ người dùng nhìn thấy.

### 4.3. Tại sao chọn dạng nhất quán quan trọng hơn tên dạng?

Một chỉ mục lưu toàn `NFC` và một chỉ mục lưu toàn `NFD` có thể thực hiện canonical equality đúng theo chính sách riêng. Nhưng không thể xây theo NFD rồi truy vấn trực tiếp theo NFC mà không chuyển đổi, vì đường ký tự/byte đã khác.

## 5. Compatibility equivalence: NFKC và NFKD

`NFKC` và `NFKD` xử lý thêm **compatibility decomposition**, nên có thể gộp các ký hiệu khác nhau về cách trình bày.

```python
import unicodedata as ud

assert ud.normalize("NFKC", "\uff21") == "A"  # Ａ
assert ud.normalize("NFKC", "\u2460") == "1"  # ①
assert ud.normalize("NFKC", "\ufb03") == "ffi"  # ﬃ
```

| Dạng | Chuẩn hóa canonical | Gộp compatibility |
| --- | --- | --- |
| `NFC` | Có | Không |
| `NFD` | Có | Không |
| `NFKC` | Có | Có |
| `NFKD` | Có | Có |

### 5.1. Gộp compatibility có thể là mất thông tin có chủ đích

Trong một ô tìm kiếm, `Ａ` và `A` có thể nên được xem tương đương. Nhưng ở một ngữ cảnh kỹ thuật, `①` và `1` có thể có nghĩa khác nhau; nếu dùng NFKC, chúng bị gộp.

**Không có dạng nào luôn là lựa chọn đúng cho mọi identifier.** Phải chọn theo yêu cầu nghiệp vụ.

### 5.2. Không biến normalization thành quy tắc bảo mật tự phát

Các chuẩn định danh như domain name hoặc tên tài khoản có thể cần quy tắc chuyên biệt, khác với “NFKC cho mọi đầu vào”. Dùng thư viện/chuẩn tương ứng khi có yêu cầu bảo mật.

## 6. Case folding khác với chuyển chữ thường

`str.lower()` là phép chuyển chữ thường thông thường. `str.casefold()` là phép gộp chữ hoa/thường mạnh hơn theo mặc định Unicode, thường dùng cho **caseless comparison**.

```python
assert "Straße".lower() == "straße"
assert "Straße".casefold() == "strasse"
assert "STRASSE".casefold() == "strasse"
```

### 6.1. Casefold có thể đổi chiều dài

`ß` thành hai ký tự `ss`. Vì vậy:

- Độ dài normalized key có thể tăng.
- Chỉ số trong normalized text có thể không khớp với chỉ số trong raw text.
- Các giá trị khác nhau theo raw string có thể trở thành một normalized key.

### 6.2. Casefold không phải locale-aware cho mọi ngôn ngữ

```python
assert "\u0130".casefold() == "i\u0307"  # İ
assert "I".casefold() == "i"
```

Đặc biệt khi sản phẩm yêu cầu xử lý chữ `I` theo quy tắc địa phương, không nên mặc định `casefold` là thuật toán đúng cho mọi locale.

### 6.3. Một pipeline dễ giải thích

```python
def nfc_casefold(text):
    text = ud.normalize("NFC", text)
    return ud.normalize("NFC", text.casefold())
```

Bước NFC sau `casefold` giúp duy trì dạng chuẩn khi phép chuyển có thể tạo ra chuỗi kết hợp. Đây là **chính sách ứng dụng cụ thể**, không phải lời khẳng định thay thế mọi định nghĩa Unicode về caseless matching.

## 7. Bỏ dấu không phải chuẩn hóa NFC

Một số sản phẩm muốn “gõ `ca` cũng tìm `cá`”. Để làm điều ấy, có thể thêm **search key không phân biệt dấu**, nhưng đây là lựa chọn **mất thông tin**.

Một ví dụ hạn chế dùng NFD và lọc dấu không giãn `Mn`:

```python
import unicodedata as ud


def strip_nonspacing_marks(text):
    decomposed = ud.normalize("NFD", text)
    kept = [
        ch for ch in decomposed
        if ud.category(ch) != "Mn"
    ]
    return ud.normalize("NFC", "".join(kept))


assert strip_nonspacing_marks("má") == "ma"
```

### 7.1. Vì sao không dùng hàm này làm chuẩn chung?

- Có nhiều loại dấu ở các hệ chữ; không phải mọi dấu đều thuộc `Mn`.
- Xóa dấu có thể đổi nghĩa từ.
- Một số chữ như `đ` không được biến thành `d` chỉ bằng NFD.
- Nhiều từ khác nhau có thể gộp về một khóa và phải lưu **posting list**.

Nếu cần tìm tiếng Việt không dấu, nên có **chính sách sản phẩm riêng và bộ kiểm thử phù hợp**, không mặc định biến đổi mọi khóa định danh theo hàm trên.

### 7.2. Các quan hệ bằng nhau có thể tách thành chỉ mục riêng

```text
raw:           "Cá"
canonical:     "Cá"
casefold:      "cá"
accent_fold:   "ca"  # nếu nghiệp vụ chủ động yêu cầu
```

Tra cứu theo `accent_fold` có thể trả nhiều ứng viên hơn, nhưng không nên thay quan hệ định danh bằng một khóa cố ý làm mất phân biệt.

## 8. Normalization không phải tokenization

Chuẩn hóa Unicode không tự quyết định:

- Gộp nhiều khoảng trắng.
- Xóa dấu câu.
- Tách từ tiếng Việt.
- Cách xử lý ký hiệu nối, URL hay email.
- Đếm emoji ghép thành một ký tự.
- Phân biệt từ đồng âm hoặc các ký hiệu trông giống nhau.

`"cà-phê"` và `"cà phê"` không tự trở thành một token chỉ vì dùng NFC.

Nếu có nhu cầu tokenization, hãy ghi **pipeline riêng**, có thứ tự các bước và phiên bản kiểm thử riêng.

## 9. Định nghĩa hàm khóa K và quan hệ bằng nhau

Một chính sách `P` tạo khóa:

\[
K_P(s)=\text{normalized key của }s.
\]

Ta định nghĩa:

\[
a\equiv_P b
\iff K_P(a)=K_P(b).
\]

Với `K_P` xác định và `==` theo code point, quan hệ ấy có tính phản xạ, đối xứng và bắc cầu.

Thứ tự so sánh có thể là:

\[
a<_P b
\iff K_P(a)<_{\mathrm{lex}}K_P(b),
\]

trong đó `<_{\mathrm{lex}}` là thứ tự từ điển của normalized key theo code point.

### 9.1. Không đổi định nghĩa ở giữa vòng đời chỉ mục

Một chỉ mục xây bằng `NFC` phân biệt hoa/thường không được tìm bằng quy tắc `NFKC + casefold` mà không **tái lập chỉ mục**.

Tương tự, Hash Map dùng hash của raw string nhưng equality theo casefold có nguy cơ phá hợp đồng tra cứu. Cách an toàn là **lưu, hash và truy vấn normalized key**.

### 9.2. Không lẫn normalized-key collision với hash collision

Hai raw string khác nhau có cùng `K_P` vì chính sách là một **quyết định ngữ nghĩa**. Hai normalized key khác nhau có cùng hash là **hash collision**, cần được Hash Map xử lý theo equality.

Đây là hai hiện tượng khác nhau.

## 10. Một key chuẩn có thể ứng với nhiều bản ghi

```python
a = "Caf\u00e9"
b = "Cafe\u0301"

assert a != b
assert ud.normalize("NFC", a) == ud.normalize("NFC", b)
```

Nếu hai bản ghi có ID khác nhau:

```text
normalized_key = "Café"

ids = ["r1", "r2"]
```

Một cấu trúc ánh xạ kiểu `normalized_key -> single_record_id` có thể **ghi đè một bản ghi** khi thêm bản ghi thứ hai.

Với tìm kiếm nhiều tài liệu, nên dùng:

```text
normalized_key -> posting list of record IDs
record_id -> original source text
```

### 10.1. Raw text là dữ liệu để hiển thị

Không nên hiển thị `"strasse"` thay cho `"Straße"` nếu giao diện cần giữ chính tả gốc. Chỉ mục có thể tìm theo khóa gộp nhưng trả **ID rồi đọc raw_text**.

### 10.2. Nếu cần uniqueness theo normalized key

Một hệ thống có thể chủ ý đặt ràng buộc “không cho hai định danh có cùng normalized key”. Nhưng đó là **quy tắc nghiệp vụ**, phải xử lý lỗi xung đột tường minh, không mặc định lấy ID sau ghi đè ID trước.

## 11. Thứ tự code point và collation ngôn ngữ

Python so `str` theo thứ tự từ điển các code point:

```python
assert "a" < "b"
assert "a" < "aa"
assert "e" < "\u00e9"
```

Đây là một quan hệ thứ tự xác định, nhưng không tự là **thứ tự từ điển tiếng Việt theo locale**.

### 11.1. So sánh code point với UTF-8 và UTF-16

Với các dãy Unicode scalar hợp lệ, UTF-8 chuẩn bảo toàn thứ tự từ điển code point khi so byte. Nhưng không nên suy ra:

- Mọi offset byte cũng là offset ký tự.
- UTF-16 code unit cũng có cùng thứ tự với code point cho mọi trường hợp.
- Collation ngôn ngữ là so mã Unicode thuần túy.

Nếu xuất/nhập chỉ mục giữa nhiều runtime, phải ghi rõ loại chuỗi, encoding, đơn vị chỉ số và comparator.

### 11.2. Collation có thể phân tầng trọng số

Collation theo một ngôn ngữ có thể điều chỉnh ưu tiên chữ cơ sở, dấu, hoa/thường và những tổ hợp ký tự.

Nếu nghiệp vụ cần, hãy dùng **collation library** thích hợp và ghi rõ locale/phiên bản. Đừng tuyên bố `sorted(list_of_names)` trong Python tự thực hiện collation tiếng Việt.

## 12. Equality và comparator phải nhất quán

Cây BST, TST hay mảng đã sắp đều có bất biến dựa trên quan hệ “nhỏ hơn”. Nếu khi xây dùng comparator A nhưng khi tìm dùng comparator B, có thể tìm sai đường hoặc sai khoảng.

Một thiết kế đơn giản:

```text
key = K_P(raw)

equality:   key_a == key_b
ordering:   key_a < key_b
hash:       hash(key)
```

Nếu nhiều ID có cùng key mà cần thứ tự bản ghi xác định, dùng **(normalized_key, record_id)** làm khóa sort record; nhưng equality theo normalized key vẫn có thể gộp nhiều ID.

### 12.1. Một comparator “bằng” khác equality là rủi ro

Giả sử comparator locale cho `cmp(a,b)==0` dù raw string khác, nhưng Hash Map dùng `a==b`. Hai cấu trúc có thể cho số lượng “khóa phân biệt” khác nhau.

Không nhất thiết sai nếu đó là chủ ý, nhưng phải **phân biệt rõ những quan hệ** và không dùng kết quả của một quan hệ như thể nó là quan hệ kia.

## 13. Ngữ nghĩa tiền tố trên normalized key

Bài học chọn:

\[
Prefix_P(q,s)
\iff K_P(s).startswith(K_P(q)).
\]

Đây **không** nhất thiết tương đương `s.startswith(q)` trên raw text.

### 13.1. NFC có thể làm tiền tố thay đổi

```python
raw = "a\u0301"
canonical = ud.normalize("NFC", raw)

assert canonical == "\u00e1"
assert raw.startswith("a")
assert not canonical.startswith("a")
```

Mặc dù raw string bắt đầu bằng code point `a`, normalized key của nó là `á`, **không bắt đầu bằng `a`**.

### 13.2. Casefold cũng có thể làm tiền tố thay đổi

```python
assert "Straße".casefold() == "strasse"
assert "strasse".startswith("stras")
assert not "Straße".startswith("stras")
```

Với `NFC + casefold`, query `"stras"` có thể khớp normalized key của `"Straße"`, dù không là tiền tố raw theo code point.

### 13.3. Normalization không phải phép phân phối qua phép nối

Nói chung có thể xảy ra:

\[
NFC(x+y)\ne NFC(x)+NFC(y).
\]

Ví dụ:

```python
x = "e"
y = "\u0301"

assert ud.normalize("NFC", x + y) == "\u00e9"
assert ud.normalize("NFC", x) + ud.normalize("NFC", y) == x + y
assert ud.normalize("NFC", x + y) != (
    ud.normalize("NFC", x) + ud.normalize("NFC", y)
)
```

**Ứng dụng streaming:** normalize từng mảnh riêng rồi nối có thể khác normalize cả văn bản. Cần thuật toán xử lý **ranh giới mảnh** đúng quy tắc Unicode.

## 14. Tiền tố và mảng khóa đã sắp

Nếu `keys` chứa các **normalized key phân biệt đã sắp theo thứ tự code point**, tất cả key có cùng prefix `q` tạo thành **một khoảng liên tiếp**.

Các bước:

1. Tạo `q=K_P(raw_query)`.
2. Tìm vị trí đầu `left=bisect_left(keys,q)`.
3. Duyệt từ `left` khi `keys[i].startswith(q)` còn đúng.
4. Trả posting list của các key khớp.

Tại sao đúng? Theo thứ tự từ điển code point, một key không có prefix `q` sẽ khác ở một ký tự trước khi hết `q` (hoặc kết thúc sớm), nên phải nằm **trước hoặc sau toàn nhóm**, không thể chen giữa hai key cùng prefix.

### 14.1. Không suy nhóm prefix luôn liên tiếp dưới mọi collation

Khi sort bằng **locale sort key** có nhiều cấp trọng số, nhóm cùng prefix code point không nhất thiết liên tiếp. Không thể dùng `bisect_left` theo một comparator nhưng `startswith` theo một quan hệ khác mà không chứng minh tính đúng.

### 14.2. Không dùng `prefix+"\uffff"` làm cận trên một cách tùy tiện

`U+FFFF` không phải code point lớn nhất của Unicode. Ký tự ngoài BMP có code point lớn hơn; cách tạo upper bound phải phụ thuộc miền ký hiệu và comparator.

Dùng `bisect_left` rồi kiểm tra `startswith` là lựa chọn dễ kiểm chứng cho ví dụ bài này.

## 15. Trie và TST phải xử lý cùng normalized key

Trong trie ký tự, mỗi cạnh tiêu thụ một ký hiệu; trong TST, nhánh `left/right` tìm ký tự khác ở cùng vị trí còn `eq` chuyển sang ký tự tiếp theo.

Nếu chính sách nói khóa là `K_P(s)`, thì:

```text
insert(raw): insert_normalized(K_P(raw))
find(raw):   find_normalized(K_P(raw))
delete(raw): delete_normalized(K_P(raw))
```

### 15.1. Nếu chỉ normalize khi chèn

Trie có thể lưu đường cho `"Café"` (chứa code point `é`), nhưng query raw `"Cafe\u0301"` đi qua `e` rồi dấu kết hợp. Nếu không chuẩn hóa query, tìm có thể thất bại dù hai biểu diễn canonical tương đương.

### 15.2. Terminal của trie có thể giữ posting list

Một terminal kiểu Set chỉ cho biết **khóa normalized tồn tại**. Nếu có nhiều bản ghi cùng key, terminal cần danh sách ID hoặc tham chiếu tới posting list.

### 15.3. Đừng sửa phép so ký tự của TST sau khi xây

TST dùng thứ tự ký tự ở mỗi tầng để chọn nhánh trái hoặc phải. Nếu đổi comparator hoặc quy tắc normalized key sau khi đã xây, các đường và bất biến BST ngang có thể không đúng.

## 16. Suffix tree và suffix array: normalized text làm đổi vị trí

Khi tìm chuỗi con, thông thường phải chuẩn hóa **toàn bộ văn bản** trước khi xây chỉ mục:

```text
original_text
      |
   normalize
      v
indexed_text
      |
   suffix tree / suffix array
      v
positions in indexed_text
```

### 16.1. Ví dụ tổ hợp dấu

```python
raw = "cafe\u0301x"
indexed = ud.normalize("NFC", raw)

assert indexed == "caf\u00e9x"
assert len(raw) == 6
assert len(indexed) == 5

assert indexed[3:4] == "\u00e9"
assert raw[3:5] == "e\u0301"
```

Truy vấn `"é"` trên `indexed` có thể trả normalized span `[3,4)`. Nhưng đoạn nguồn tương ứng là `raw[3:5]`. Nếu dùng trực tiếp `raw[3:4]` để tô sáng, **dấu sắc sẽ bị bỏ sót**.

### 16.2. Casefold mở rộng một code point

```python
raw = "Straße"
indexed = ud.normalize("NFC", raw.casefold())

assert indexed == "strasse"
assert len(raw) == 6
assert len(indexed) == 7
```

Trong normalized text, `"ss"` tương ứng với một `ß` ở nguồn. Một truy vấn khớp **một phần** đoạn mở rộng không nhất thiết có substring nguồn cùng chiều dài và cùng giá trị normalized.

### 16.3. Offset mapping là yêu cầu riêng của ứng dụng

Nếu muốn tô sáng chính xác raw text, cần ánh xạ normalized span sang **source span**. Ánh xạ có thể là **nhiều-to-một hoặc một-to-nhiều**, nên không được giả định `source_offset=normalized_offset`.

Đồng thời, chi phí bộ nhớ của bảng ánh xạ cần được tính vào hệ thống tìm kiếm, không bỏ khỏi phép đo RAM chỉ vì bản suffix array/tree có O(n) bộ nhớ.

## 17. Grapheme segmentation và giới hạn của cách xử lý thủ công

Unicode Grapheme Cluster Boundary phức tạp hơn “gắn mọi dấu kết hợp vào ký tự trước”. Emoji ghép bằng `ZWJ`, regional indicator, variation selector và nhiều hệ chữ có quy tắc đặc biệt.

### 17.1. Không normalize từng code point riêng rồi nối

```python
x = "e"
mark = "\u0301"

whole = ud.normalize("NFC", x + mark)
pieces = (
    ud.normalize("NFC", x)
    + ud.normalize("NFC", mark)
)

assert whole != pieces
```

Một kết quả normalize ở cấp **toàn chuỗi** có thể thay đổi ranh giới giữa hai code point nguồn.

### 17.2. Không coi `unicodedata.combining` là grapheme segmenter đầy đủ

`unicodedata.combining` cung cấp canonical combining class của một code point, nhưng **không triển khai đầy đủ Unicode Text Segmentation**. Nếu sản phẩm cần offset theo grapheme, hãy dùng bộ phân đoạn tuân chuẩn tương ứng, có phiên bản và kiểm thử.

### 17.3. Một mẫu metadata ánh xạ

```text
NormalizedSpan:
    normalized_start
    normalized_end
    source_start
    source_end
```

Các ranh giới ở đây phải ghi rõ đơn vị và quy tắc gộp khi một span normalized không tương ứng một-một với raw text. Đừng tự hứa rằng có thể ánh xạ mọi code point bằng một phép cộng offset.


## 18. Thiết kế chính sách tạo khóa có thể kiểm chứng

Để không phụ thuộc vào suy đoán của từng hàm, đặt chính sách dưới dạng một đối tượng bất biến:

```text
Policy:
    form         = NFC | NFD | NFKC | NFKD
    ignore_case  = true | false
    key_order    = Unicode code point lexicographic
```

Hàm tạo khóa:

```text
key = normalize(form, raw)

if ignore_case:
    key = normalize(form, casefold(key))
```

### 18.1. Tại sao normalize sau casefold?

Một phép biến đổi chữ hoa/thường có thể trả về nhiều code point, gồm dấu kết hợp. Chuẩn hóa lại giúp bảo đảm kết quả tuân dạng đã chọn.

### 18.2. Chính sách này có giới hạn

Đây là một **hợp đồng do ứng dụng định nghĩa**, không phải tuyên bố thực thi tất cả phiên bản, locale và chế độ *default caseless matching* được chuẩn Unicode mô tả trong mọi ngữ cảnh.

Nếu dùng cho identifier bảo mật, domain, các giao thức chuẩn hoặc dữ liệu cần so khớp locale đặc thù, phải áp dụng **chuẩn riêng của miền đó**.

### 18.3. Nguyên tắc không làm mất raw text

Hệ thống lưu:

```text
record_id -> raw_text
normalized_key -> list[record_id]
```

Không dùng normalized key thay `record_id` nếu nhiều bản ghi được phép trùng tên hoặc nếu chính sách có thể gộp các chuỗi khác nhau.

## 19. Python: định nghĩa chính sách tạo normalized key

Ta dùng `dataclass(frozen=True)` để tránh thay đổi cấu hình của một đối tượng policy sau khi đã xây chỉ mục.

```python
from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class KeyPolicy:
    form: str = "NFC"
    ignore_case: bool = False

    def __post_init__(self):
        allowed = ("NFC", "NFD", "NFKC", "NFKD")
        if self.form not in allowed:
            raise ValueError("form Unicode không hợp lệ")
        if type(self.ignore_case) is not bool:
            raise TypeError("ignore_case phải là bool")

    def key(self, value):
        if not isinstance(value, str):
            raise TypeError("khóa phải là str")

        result = unicodedata.normalize(self.form, value)

        if self.ignore_case:
            result = unicodedata.normalize(
                self.form, result.casefold()
            )

        return result
```

### 19.1. Kiểm tra ba chính sách

```python
canonical = KeyPolicy("NFC", ignore_case=False)
folded = KeyPolicy("NFC", ignore_case=True)
compat = KeyPolicy("NFKC", ignore_case=False)

assert canonical.key("\u00e9") == canonical.key("e\u0301")
assert folded.key("Straße") == folded.key("STRASSE")
assert compat.key("\uff21") == "A"
assert compat.key("\u2460") == "1"

assert canonical.key("Café") != canonical.key("café")
assert folded.key("Café") == folded.key("CAFÉ")
assert canonical.key("Cafe") != canonical.key("Café")
```

### 19.2. “Frozen” chưa đủ để tái tạo kết quả ở mọi phiên bản

`frozen=True` chỉ giữ hai trường cấu hình không đổi. Nó không cố định phiên bản cơ sở dữ liệu Unicode mà Python `unicodedata` sử dụng, cũng không cố định phiên bản thư viện collation bên ngoài.

Một chỉ mục cần tái lập nên ghi thêm **Unicode data version** và **phiên bản chính sách**.

## 20. Cài đặt chỉ mục bản ghi với normalized key và posting list

Cài đặt sau dùng:

- `original_by_id`: giữ raw string theo ID.
- `ids_by_key`: normalized key → danh sách ID.
- `sorted_keys`: các normalized key **phân biệt, đã sắp theo code point**.

Nó hỗ trợ `exact(query)` và `prefix(query,limit)`, và không ghi đè hai bản ghi có cùng normalized key.

```python
from bisect import bisect_left


class NormalizedKeyIndex:
    def __init__(self, records, policy):
        if not isinstance(policy, KeyPolicy):
            raise TypeError("policy phải là KeyPolicy")

        self.policy = policy
        self.original_by_id = {}
        self.ids_by_key = {}

        for record_id, raw_text in records:
            if not isinstance(record_id, str):
                raise TypeError("record_id phải là str")

            if record_id in self.original_by_id:
                raise ValueError("record_id bị trùng")

            key = policy.key(raw_text)
            self.original_by_id[record_id] = raw_text
            self.ids_by_key.setdefault(key, []).append(record_id)

        self.sorted_keys = sorted(self.ids_by_key)

    def exact(self, query):
        """Danh sách ID có normalized key bằng query key."""
        key = self.policy.key(query)
        return list(self.ids_by_key.get(key, ()))

    def prefix(self, query, limit=None):
        """Danh sách ID theo normalized key tăng.

        Các ID cùng key giữ thứ tự records đầu vào.
        """
        if limit is not None and (
            type(limit) is not int or limit < 0
        ):
            raise ValueError("limit phải là None hoặc int >= 0")

        key_prefix = self.policy.key(query)

        if limit == 0:
            return []

        left = bisect_left(self.sorted_keys, key_prefix)
        result = []

        for pos in range(left, len(self.sorted_keys)):
            key = self.sorted_keys[pos]

            if not key.startswith(key_prefix):
                break

            for record_id in self.ids_by_key[key]:
                result.append(record_id)

                if limit is not None and len(result) == limit:
                    return result

        return result

    def display_text(self, record_id):
        return self.original_by_id[record_id]
```

### 20.1. Vì sao `sorted_keys` chỉ chứa khóa phân biệt?

Có thể có nhiều bản ghi cùng một normalized key. Mảng tìm tiền tố chỉ cần **một phần tử cho mỗi normalized key**, còn các ID thuộc nhóm đó được lấy từ posting list.

Điều này tránh việc phải so lại normalized key giống nhau của từng bản ghi khi binary search.

### 20.2. Tại sao không dùng lát cắt `sorted_keys[left:]`?

Việc cắt Python list tạo một danh sách mới, có thể chứa rất nhiều tham chiếu nếu chỉ mục lớn. Vòng lặp theo chỉ số chỉ giữ thêm vài biến cục bộ, trong khi danh sách kết quả được tạo khi thực sự có ID khớp.

### 20.3. Đây là chỉ mục tĩnh

Sau khi xây, `sorted_keys` không được cập nhật. Nếu chèn một normalized key mới vào giữa Python list, có thể cần **dịch O(U) phần tử**. Với ứng dụng cập nhật liên tục, nên xem xét:

- Duy trì cấu trúc có thứ tự hỗ trợ cập nhật.
- Trie hay B-tree.
- Ghi log cập nhật và rebuild theo lô.
- Chỉ mục phụ cho phần mới thay đổi.

### 20.4. Hợp đồng thứ tự của kết quả

`prefix` trả nhóm theo **normalized key tăng theo code point**. Trong mỗi nhóm, các ID giữ **thứ tự xuất hiện trong dữ liệu đầu vào**. Đây không phải cam kết thứ tự từ điển tiếng Việt theo locale.

## 21. Ví dụ đối chiếu exact và prefix

```python
policy = KeyPolicy("NFC", ignore_case=True)

index = NormalizedKeyIndex(
    [
        ("r1", "Caf\u00e9"),
        ("r2", "Cafe\u0301"),
        ("r3", "Cafe"),
        ("r4", "cafeteria"),
        ("r5", "Straße"),
        ("r6", "STRASSE"),
    ],
    policy,
)

# Canonical và casefold: nhiều nguồn cùng key.
assert index.exact("CAF\u00c9") == ["r1", "r2"]
assert index.exact("cafe\u0301") == ["r1", "r2"]
assert index.exact("strasse") == ["r5", "r6"]

# NFC+casefold không phải bỏ dấu.
assert index.exact("cafe") == ["r3"]
assert index.prefix("cafe") == ["r3", "r4"]
assert index.prefix("caf\u00e9") == ["r1", "r2"]
assert index.prefix("stras") == ["r5", "r6"]

# Code point e < é.
assert index.prefix("ca") == [
    "r3", "r4", "r1", "r2"
]

assert index.prefix("caf", limit=3) == [
    "r3", "r4", "r1"
]

assert index.prefix("no-such-prefix") == []
assert index.prefix("ca", limit=0) == []
assert index.display_text("r2") == "Cafe\u0301"
```

### 21.1. Giải thích vì sao `"cafe"` không tìm thấy `"Café"`

Các khóa sau NFC+casefold là:

```text
"Cafe"       -> "cafe"
"cafeteria"  -> "cafeteria"
"Café"       -> "café"
"Cafe\u0301" -> "café"
```

`"café"` không bắt đầu bằng **bốn code point** `"cafe"`. Người dùng muốn tìm không dấu thì cần một **search key bỏ dấu** riêng.

### 21.2. Vì sao `prefix("ca")` trả r3, r4 rồi mới r1, r2?

Theo thứ tự code point, `"cafe" < "cafeteria" < "café"`. Thứ tự đó là hợp đồng kỹ thuật của chỉ mục, không phải lời khẳng định về thứ tự hiển thị ngôn ngữ tự nhiên.

## 22. Độ phức tạp của chỉ mục normalized key

Đặt:

- `R`: số bản ghi.
- `U`: số normalized key phân biệt, `U≤R`.
- `S`: tổng chiều dài các chuỗi nguồn.
- `Q`: chiều dài query trước chuẩn hóa.
- `P`: chiều dài normalized query.
- `K`: chiều dài normalized key dài nhất.
- `J`: số normalized key phân biệt khớp prefix.
- `M`: tổng số record ID được trả.

### 22.1. Xây chỉ mục

Các bước:

1. Tạo normalized key cho R chuỗi.
2. Thêm ID vào Hash Map theo key.
3. Sắp U key phân biệt.

Chi phí chuẩn hóa phụ thuộc **thuật toán và dữ liệu Unicode**, thường gần tuyến tính theo chiều dài trong triển khai tốt, nhưng không nên gắn một chặn worst-case tuyến tính tuyệt đối nếu chưa xét việc sắp dấu kết hợp và thuật toán cụ thể.

Sắp U chuỗi bằng comparator từ điển cần O(U log(U+1)) phép so trong trường hợp xấu; mỗi phép so có thể đọc tối đa O(K) code point. Chặn đơn giản:

\[
T_{\mathrm{sort}}=O(UK\log(U+1)).
\]

Cộng thêm chi phí tạo khóa và các phép Hash Map.

### 22.2. Truy vấn chính xác

`exact` chuẩn hóa query rồi tra dictionary:

\[
T_{\mathrm{exact}}
=
T_{\mathrm{normalize}}(Q)+O(P+M)
\]

**kỳ vọng** với giả định hash dictionary phù hợp, tính cả việc băm chuỗi khóa P ký tự và xuất M ID.

### 22.3. Truy vấn prefix

`bisect_left` dùng O(log(U+1)) phép so chuỗi, mỗi phép có thể xem tới K code point. Sau đó so `startswith` với J key khớp và tối đa một key không khớp, rồi xuất M ID.

Một chặn đơn giản:

\[
T_{\mathrm{prefix}}=
T_{\mathrm{normalize}}(Q)
+O(K\log(U+1)+JP+M+P).
\]

Nếu `limit` nhỏ, số ID duyệt có thể giảm. Nhưng không thể gọi O(limit) vì **còn chi phí chuẩn hóa, tìm biên và xét key**.

### 22.4. Bộ nhớ

Ngoài raw text:

- U normalized key với tổng chiều dài có thể khác S vì NFC/NFKC/casefold có thể co hoặc nở.
- U phần tử mảng `sorted_keys`.
- R ID trong posting lists.
- Overhead `dict`, `list`, `str` và số liệu của runtime.

Độ phức tạp không phải O(R) **byte** độc lập với chiều dài khóa; cần tính **tổng chiều dài key** và overhead thực tế.

## 23. So sánh với trie và TST

| Tiêu chí | Trie ký tự | TST | Mảng normalized key đã sắp |
| --- | --- | --- | --- |
| Tìm tiền tố | Đi theo P ký tự | Tìm ký tự qua trái/bằng/phải | Binary search tới khoảng tiền tố |
| Chi phí định vị | O(P) kỳ vọng nếu mỗi cạnh chọn O(1) | Phụ thuộc các BST ngang | O(K log U) chặn đơn giản |
| Liệt kê | Duyệt cây con | Duyệt `eq`/nhánh ngang phù hợp | Quét key liên tiếp |
| Bộ nhớ | Nút/cạnh và nhánh | Nút ba liên kết | Các key, mảng và posting lists |
| Cập nhật | Có thể thao tác tại đường khóa | Có thể thao tác tại đường ký tự | Chèn key mới có thể dịch list |
| Sắp theo code point | Theo nhánh đã sắp | Theo DFS trái–node–giữa–phải | Theo mảng đã sort |
| Sắp theo locale | Chính sách bổ sung | Chính sách bổ sung | Chính sách bổ sung |

Các phép tìm đều phải dùng **cùng normalized key**. Chọn cấu trúc sau khi đã chốt ngữ nghĩa; đổi cấu trúc không tự giải quyết bất đồng về Unicode.

## 24. Tách sort hiển thị theo locale khỏi tìm tiền tố

Một hệ thống có thể:

1. Tạo normalized key cho mục tiêu tìm.
2. Dùng trie hoặc mảng để chọn các ID khớp tiền tố.
3. Dùng một **locale sort key** để xếp các ID được trả về.
4. Hiển thị raw text.

```text
source records
      |
  K_search(raw)
      |
 prefix index
      |
 matched IDs
      |
 locale sort key + stable ID
      |
 display result
```

### 24.1. Tại sao không dùng locale comparator cho mọi thứ?

Các thuật toán binary search theo prefix yêu cầu nhóm cùng tiền tố **liền nhau trong quan hệ so sánh đang dùng**. Một comparator dựa trên nhiều cấp trọng số ngôn ngữ không tự bảo đảm nhóm cùng **tiền tố code point** liền nhau.

Nếu cần dùng locale sort key trong một cấu trúc có thứ tự, phải chứng minh tính đúng của truy vấn được dùng trên **chính thứ tự ấy**.

### 24.2. Cần tie-break ổn định

Hai bản ghi có cùng locale sort key vẫn có thể khác ID. Nếu cần kết quả tái lập, hãy thêm ID vào khóa sắp, chẳng hạn `(display_sort_key, record_id)`.

## 25. Unicode security: confusable khác canonical equivalent

Một số ký tự thuộc hai hệ chữ khác nhau có thể **trông rất giống nhau** nhưng không thuộc cùng canonical/compatibility equivalence. NFC và NFKC **không phải** bộ phát hiện mọi ký tự gây nhầm lẫn (*confusable*).

### 25.1. Nếu dùng cho identifier nhạy cảm

Cần cân nhắc:

- Quy tắc cho phép/từ chối script.
- Kiểm tra trộn hệ chữ nếu nghiệp vụ yêu cầu.
- Xử lý ký tự điều khiển hướng chữ.
- Các chuẩn chuyên biệt cho tên tài khoản/domain.
- Cơ chế đánh giá confusable có phiên bản.

Không dùng một khóa tìm kiếm cố ý gộp nhiều bản ghi làm khóa xác thực nếu không có đặc tả định danh chặt chẽ.

### 25.2. Không tự xóa ký tự vô hình

Một số ký tự ít thấy trên màn hình vẫn có vai trò ngôn ngữ hoặc kết hợp emoji. Xóa tất cả ký tự zero-width một cách máy móc có thể làm đổi nội dung hợp lệ.

Cần phân biệt **chính sách lọc dữ liệu đầu vào** với **Unicode normalization**.

## 26. Phiên bản Unicode và tái lập chỉ mục

Python cung cấp:

```python
import unicodedata

unicode_data_version = unicodedata.unidata_version
```

Đó là phiên bản cơ sở dữ liệu Unicode của `unicodedata` trong runtime đang dùng.

### 26.1. Một manifest chỉ mục hữu ích

```text
index_schema_version = <actual schema version>
normalization_form   = NFC
ignore_case          = true
unicode_data_version = <actual runtime value>
comparison_rule      = Unicode code point lexicographic
offset_unit          = code point in normalized text
source_snapshot_id   = <source version>
```

Đây là **ví dụ cấu trúc metadata**, không phải một manifest đã được điền phiên bản thật. Trong sản phẩm cần ghi **các giá trị thực** lúc build.

Nếu dùng locale collation, bổ sung locale và phiên bản thư viện liên quan.

### 26.2. Khi nâng runtime/chính sách

Một quy trình an toàn:

1. Xác định cấu hình và phiên bản cũ/mới.
2. Tạo lại normalized key từ **raw source**.
3. Phát hiện những collision mới do thay chính sách.
4. Xây lại Hash Map/Trie/TST/SA hoặc mảng key đã sắp.
5. So kết quả exact, prefix và thứ tự trên bộ dữ liệu chuẩn.
6. Chuyển sang chỉ mục mới và có kế hoạch rollback khi cần.

Không được chỉ đổi `KeyPolicy` phía truy vấn trong khi dữ liệu đã được lập chỉ mục theo chính sách cũ.

## 27. Bộ kiểm thử: từ equivalence tới thứ tự và offset

Kiểm thử cần bao phủ những lớp khác nhau:

| Nhóm | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| Canonical | `é` / `e + dấu` | Khớp sau NFC |
| Compatibility | `Ａ` / `A` | Trùng theo NFKC |
| Casefold | `Straße` / `STRASSE` | Trùng khi ignore_case |
| Giữ dấu | `cafe` / `café` | Không trùng chỉ vì NFC |
| Prefix | `a` / `a + dấu` | Raw prefix khác normalized prefix |
| Unicode dài | Emoji, ký tự ngoài BMP | Offset không bị nhầm đơn vị |
| Trùng normalized key | Hai raw record | Không mất bản ghi |
| Query rỗng | `""` | Prefix trả mọi key |
| Limit | 0, 1, nhiều | Dừng đúng |
| Nâng phiên bản | Chính sách cũ/mới | Phát hiện nhu cầu rebuild |

### 27.1. Kiểm tra độc lập tính liên tiếp của nhóm prefix

```python
policy = KeyPolicy("NFC", ignore_case=True)

raw_keys = [
    "Caf\u00e9", "Cafe\u0301", "Cafe",
    "cafeteria", "Straße", "STRASSE",
]

keys = sorted(set(map(policy.key, raw_keys)))

for query in ("", "ca", "caf", "cafe", "caf\u00e9", "str"):
    prefix = policy.key(query)

    expected = [
        key for key in keys
        if key.startswith(prefix)
    ]

    if expected:
        left = keys.index(expected[0])
        assert keys[left:left + len(expected)] == expected
```

Đây là oracle độc lập dựa trên `startswith` cho **tập thử nhỏ**, giúp kiểm tra tính liên tiếp trong thứ tự code point. Nó không chứng minh tính chất tương tự cho mọi locale comparator.

### 27.2. Kiểm tra raw text vẫn được bảo toàn

```python
assert index.display_text("r1") == "Caf\u00e9"
assert index.display_text("r2") == "Cafe\u0301"
assert index.display_text("r1") != index.display_text("r2")
```

Hai bản ghi có thể xuất hiện cùng kết quả exact, nhưng nội dung nguồn vẫn khác nhau và được giữ nguyên.

### 27.3. Bộ kiểm thử không thay thế QA sản phẩm

Với hệ thực tế, cần thêm corpus đa ngôn ngữ, dấu kết hợp phức tạp, dữ liệu ngoài BMP, trường hợp confusable và các biểu diễn identifier theo chính sách ngành. Cần đo thực tế độ trễ và bộ nhớ của từng cấu trúc.

## 28. Tình huống: danh bạ tên tiếng Việt

Một danh bạ lưu:

```text
id=1  "Café"
id=2  "Cafe\u0301"
id=3  "Cafe"
id=4  "Cà phê"
id=5  "cafe"
```

Yêu cầu:

- Hiển thị tên đúng dạng nguồn.
- Exact search theo canonical equivalence.
- Có chế độ tìm không phân biệt hoa/thường.
- Có thể hỗ trợ tìm không dấu, nếu người dùng chọn.
- Có thứ tự hiển thị tiếng Việt phù hợp với sản phẩm.

### 28.1. Thiết kế nhiều chỉ mục

```text
records:
    id -> raw text

canonical_index:
    NFC(raw) -> list[id]

casefold_index:
    NFC(casefold(NFC(raw))) -> list[id]

optional_accent_index:
    product_defined_accent_fold(raw) -> list[id]

display_sort:
    locale_sort_key(raw), then stable id
```

### 28.2. Vì sao không chỉ có một normalized key?

Vì những nhu cầu trên định nghĩa **các quan hệ khác nhau**:

- Hai dạng Unicode của `Café` cần chung canonical key.
- `Cafe` và `cafe` có thể cần chung casefold key.
- `Café` và `Cafe` chỉ nên gộp ở chế độ tìm không dấu.
- Display sort còn phụ thuộc locale và cách viết nguồn.

### 28.3. Chi phí của nhiều chỉ mục

Nhiều key và posting list làm tăng RAM và chi phí cập nhật. Nếu một bản ghi đổi tên, phải cập nhật **tất cả** chỉ mục liên quan trong một cơ chế nhất quán.

Đây là đánh đổi giữa **phục vụ nhiều kiểu tra cứu** và **chi phí lưu trữ, đồng bộ**.

## 29. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Xem hiển thị giống nhau là raw `==` | Bỏ sót canonical equivalent | Dùng normalization nhất quán |
| Xem NFC là bỏ dấu | Query không dấu có thể không khớp | Bỏ dấu là chính sách riêng |
| Dùng NFKC cho mọi identifier | Gộp compatibility không mong muốn | Chọn theo miền dữ liệu |
| Dùng `lower` và gọi là casefold | Bỏ sót trường hợp mở rộng `ß` | Phân biệt hai phép |
| Xem `casefold` là mọi locale | Sai quy tắc địa phương | Thiết kế locale riêng |
| Chỉ normalize khi chèn | Truy vấn bản khác có thể thất bại | Normalize query giống lúc build |
| Chỉ normalize lúc tìm | Index raw không tương thích | Rebuild theo chính sách |
| Dùng key chuẩn để hiển thị | Mất cách viết nguồn | Giữ raw text theo ID |
| `dict[key]=id` khi nhiều bản ghi | Ghi đè ID | Posting list |
| Trộn comparator và equality | Binary search, BST, Hash Map bất nhất | Hợp đồng thống nhất |
| Normalizing từng mảnh rồi nối | Sai ở biên dấu kết hợp | Xử lý ranh giới đúng |
| Cho rằng NFC luôn giữ chiều dài | Offset lệch | Mapping normalized→source |
| Cho rằng casefold giữ 1:1 | `ß` thành `ss` | Hỗ trợ span nhiều–một |
| Gọi `len(str)` là số grapheme | Sai với emoji và dấu kết hợp | Unicode segmentation |
| Gọi `sorted` là collation tiếng Việt | Thứ tự code point khác locale | Sort key riêng |
| Dùng binary search theo comparator khác lúc build | Sai khoảng tìm | Cùng một comparator |
| Đồng nhất prefix raw và normalized | Truy vấn mất/nhận khác dự kiến | Ghi rõ ngữ nghĩa prefix |
| Dùng `prefix+"\uffff"` làm upper bound tuyệt đối | Bỏ sót ký tự lớn hơn U+FFFF | Chứng minh successor hoặc scan |
| Dùng NFKC để chống mọi spoof | Confusable chưa được xử lý | Quy tắc identifier chuyên dụng |
| Nâng Unicode runtime mà không xét version | Key có thể lệch | Metadata, rebuild |
| Bỏ chi phí normalize và lưu postings | Ước lượng thời gian/RAM sai | Đo toàn pipeline |
| Không kiểm tra trùng record ID | Mất dữ liệu gốc | Kiểm tra ID khi xây |

## 30. Bài tập vận dụng có gợi ý

### Bài 1 — Canonical equivalence

`"\u00e9"` và `"e\u0301"` có bằng nhau bằng `==` trên Python `str` không? Qua NFC thì sao?

**Gợi ý:** Raw khác nhau; sau NFC bằng nhau.

### Bài 2 — Byte và code point

`len("\u00e9")` và `len("e\u0301")` là bao nhiêu? Hai dạng có bao nhiêu byte UTF-8?

**Gợi ý:** 1 và 2 code point; 2 và 3 byte UTF-8.

### Bài 3 — Chọn normalization form

Muốn gộp `"Ａ"` với `"A"`, NFC có đủ không?

**Gợi ý:** Không; NFKC xử lý compatibility.

### Bài 4 — Compatibility và rủi ro

Tại sao một hệ ID có thể không muốn gộp `"①"` với `"1"`?

**Gợi ý:** Chúng có thể là hai mã khác nhau dù NFKC biến giống nhau.

### Bài 5 — Casefold

So kết quả `"Straße".lower()` và `"Straße".casefold()`.

**Gợi ý:** `straße` và `strasse`.

### Bài 6 — Giữ dấu

Với NFC+casefold, `"Cafe"` và `"Café"` có cùng normalized key không?

**Gợi ý:** Không. Casefold không xóa dấu.

### Bài 7 — Prefix raw và normalized

Vì sao raw `"a\u0301"` bắt đầu bằng `"a"` nhưng NFC key không bắt đầu bằng `"a"`?

**Gợi ý:** NFC tổ hợp thành code point `á`.

### Bài 8 — Normalize trước và sau nối

Cho `x="e"` và `y="\u0301"`. Giải thích vì sao `NFC(x+y)` khác `NFC(x)+NFC(y)`.

**Gợi ý:** Vế đầu dựng sẵn `é`, vế sau còn dãy `e` + dấu.

### Bài 9 — Posting list

Hai bản ghi khác ID nhưng normalized key giống nhau. Nên lưu gì dưới key?

**Gợi ý:** Danh sách ID, không ghi đè một ID.

### Bài 10 — Hash và equality

Tại sao không nên so equality theo casefold nhưng hash raw text?

**Gợi ý:** Hợp đồng tra cứu đòi những khóa được coi bằng nhau có hash/đường tra tương thích.

### Bài 11 — Khoảng tiền tố

Tại sao nhóm key cùng prefix liên tiếp khi sort theo code point?

**Gợi ý:** Key khác tiền tố phải nằm trước hoặc sau cả nhóm tại vị trí khác đầu tiên.

### Bài 12 — Collation

Vì sao `sorted` trên Python `str` không bảo đảm thứ tự tiếng Việt theo sản phẩm?

**Gợi ý:** Nó so code point, không dùng locale collation.

### Bài 13 — Offset sau NFC

`raw="cafe\u0301x"`, kết quả tìm `é` trong NFC text là `[3,4)`. Span nguồn tương ứng là gì?

**Gợi ý:** `raw[3:5]`, gồm chữ `e` và dấu.

### Bài 14 — Offset sau casefold

Vì sao `source_offset=normalized_offset` sai khi `ß` biến thành `ss`?

**Gợi ý:** Một code point nguồn thành hai code point kết quả.

### Bài 15 — Grapheme

Một emoji ghép có luôn làm `len(str)` tăng đúng 1 không?

**Gợi ý:** Không; Python đếm code point.

### Bài 16 — Trie/TST

Một trie được xây trên NFC key nhưng query không normalize. Lỗi gì có thể xuất hiện?

**Gợi ý:** Đường ký tự khác nhau giữa dạng dựng sẵn và tách dấu.

### Bài 17 — Suffix array

Nếu suffix array xây trên normalized text, chỉ số xuất hiện trả về thuộc chuỗi nào?

**Gợi ý:** Normalized text; cần mapping để tô sáng nguồn.

### Bài 18 — Đổi policy

Chỉ mục NFC phân biệt hoa/thường; muốn bật casefold, chỉ đổi hàm query có đủ không?

**Gợi ý:** Không, phải tạo lại normalized key và rebuild.

### Bài 19 — Độ phức tạp sort

Có U normalized key dài tối đa K. Chặn sort theo phép so code point là gì?

**Gợi ý:** O(UK log(U+1)) trong mô hình so code point O(1).

### Bài 20 — Thiết kế nhiều quan hệ

Một hệ cần ID chính xác, tìm tên không phân biệt hoa/thường và sắp hiển thị theo locale. Có nên dùng duy nhất một key cho mọi thao tác?

**Gợi ý:** Thường tách ID, search key, display sort key, giữ raw text và version.

## 31. Checklist thiết kế chỉ mục Unicode

```text
1. Ngữ nghĩa:
   - Equality canonical hay compatibility?
   - Có casefold không?
   - Có chính sách bỏ dấu độc lập?
   - Tokenization có được đặc tả riêng?
   - Prefix của raw hay normalized key?

2. Unicode:
   - Dùng NFC, NFD, NFKC hay NFKD?
   - Đơn vị chỉ số: byte, code point, UTF-16 hay grapheme?
   - Có xử lý emoji/dấu kết hợp?
   - Runtime Unicode version có được ghi lại?
   - Có cần locale collation?

3. Bất biến chỉ mục:
   - Chèn, tìm, xóa dùng cùng K_P?
   - Hash và equality tương thích?
   - BST/TST/SA dùng cùng comparator đã build?
   - Trùng normalized key có giữ mọi record ID?
   - Raw text còn nguyên để hiển thị?

4. Prefix:
   - Khoảng khớp theo thứ tự code point?
   - Nếu dùng locale sort, prefix group còn liên tiếp không?
   - Query rỗng có hợp đồng rõ?
   - Limit không loại kết quả sai thứ tự?

5. Offset:
   - Vị trí trả trong normalized text hay source?
   - Có trường hợp 1-to-many hoặc many-to-1?
   - Có mapping normalized span -> source span?
   - Có chính sách tô sáng nếu match một phần expansion?
   - Có tính RAM mapping?

6. Vận hành:
   - Metadata form/casefold/Unicode/locale có phiên bản?
   - Đổi policy có rebuild chỉ mục?
   - Trước khi rebuild có phát hiện collision mới?
   - Có phân biệt search key và identifier bảo mật?
   - Có cơ chế kiểm tra confusable khi cần?

7. Kiểm thử và hiệu năng:
   - Chuỗi rỗng, dạng kết hợp, compatibility, ß?
   - Ký tự ngoài BMP và chuỗi emoji?
   - Raw prefix khác normalized prefix?
   - Tìm exact và prefix so với oracle đơn giản?
   - Đã đo RAM raw, key, posting list và sort?
   - Đã thử nâng runtime/phần mềm?
```

## 32. Tổng kết

**Đặc tả so sánh khóa là một phần của tính đúng cấu trúc dữ liệu.** Unicode cho phép những chuỗi nhìn giống nhau có dãy code point khác nhau; NFC/NFD giải quyết canonical equivalence, NFKC/NFKD có thể gộp compatibility, và casefold xử lý hoa/thường theo chính sách Unicode mặc định nhưng **không tự bỏ dấu hay sắp theo locale**.

Một hệ thống chỉ mục đáng tin cậy cần:

- Giữ **raw text** và tạo **normalized key** theo chính sách có phiên bản.
- Dùng cùng chính sách ở **chèn, tra, xóa, hash và sắp thứ tự**.
- Bảo toàn **posting list** khi nhiều bản ghi cho cùng key.
- Định nghĩa prefix theo **raw hay normalized key**, không giả định hai khái niệm tương đương.
- Tách **thứ tự tìm kỹ thuật** khỏi **thứ tự hiển thị theo locale** nếu cần.
- Ghi rõ **đơn vị offset**, xây ánh xạ về nguồn khi biến đổi Unicode thay đổi chiều dài.
- Kiểm thử canonical, compatibility, casefold, Unicode phức tạp và đường nâng phiên bản.

Trie, TST, Hash Map, suffix tree và suffix array chỉ phát huy đúng ưu thế về thời gian–bộ nhớ khi **bất biến Unicode và quan hệ so sánh khóa được áp dụng thống nhất**. Không một độ phức tạp tốt nào bù đắp được việc lúc xây và lúc truy vấn dùng hai định nghĩa “bằng nhau” khác nhau.
