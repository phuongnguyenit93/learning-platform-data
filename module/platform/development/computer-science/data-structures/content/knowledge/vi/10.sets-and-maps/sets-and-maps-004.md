# Phân biệt thiếu khóa với giá trị rỗng hợp lệ

Trong hệ thống quản lý kho, mã sản phẩm `SP01` có thể tồn tại với số lượng **0** vì đã hết hàng, còn `SP99` có thể **chưa từng được đăng ký**. Cả hai trường hợp đều không có hàng để giao ngay, nhưng ý nghĩa dữ liệu khác nhau: sản phẩm hết hàng có thể được bổ sung tồn kho; sản phẩm chưa đăng ký cần được tạo mới hoặc báo lỗi mã.

Tương tự, một cài đặt `email_notifications = False` nghĩa là người dùng **đã chủ động tắt** thông báo, khác với việc chưa đặt tùy chọn. Trong chương **Tập hợp và ánh xạ**, sự phân biệt này là điều kiện quan trọng để thực hiện đúng các thao tác thêm, cập nhật, tra cứu và xóa theo khóa. Bài học áp dụng vào việc chọn cấu trúc dữ liệu và đánh giá độ phức tạp thời gian, bộ nhớ trong module cấu trúc dữ liệu.

## 1. Hai câu hỏi khác nhau khi tra cứu map

**Map** (ánh xạ) là kiểu dữ liệu trừu tượng lưu các cặp khóa–giá trị, trong đó mỗi khóa phân biệt có tối đa một giá trị tại một thời điểm. Với map `M` và khóa `k`, ta cần phân biệt:

1. **Khóa có tồn tại không?** Kiểm tra `k ∈ dom(M)`, trong đó `dom(M)` là tập khóa hiện có.
2. **Nếu khóa tồn tại, giá trị của nó là gì?** Lấy `M[k]`.

Về mặt ngữ nghĩa, phép tra cứu đầy đủ có hai kiểu kết quả:

```text
LOOKUP(M, k):
    nếu k thuộc tập khóa của M:
        trả FOUND(value = M[k])
    ngược lại:
        trả NOT_FOUND
```

`FOUND(None)` và `NOT_FOUND` là **hai trạng thái khác nhau** nếu `None` là giá trị được phép lưu. Kết quả chỉ là `None` không đủ thông tin để phân biệt chúng.

Ví dụ:

```python
products = {
    "SP01": 0,       # Có sản phẩm, số lượng bằng 0
    "SP02": None,    # Có sản phẩm, chưa kiểm kê
    "SP03": 12,      # Có sản phẩm, còn 12 đơn vị
}

print("SP01" in products)  # True
print("SP02" in products)  # True
print("SP99" in products)  # False
```

Nếu chương trình gọi `products.get("SP02")` và `products.get("SP99")`, cả hai đều trả `None` theo mặc định. **Tính hiện diện của khóa đã bị mất** trong một kết quả như vậy.

### “Rỗng” có nhiều nghĩa

Không nên xem tất cả giá trị có vẻ rỗng là cùng một trạng thái. Bảng sau minh họa các giá trị hoàn toàn hợp lệ trong map Python:

| Giá trị | Ví dụ dữ liệu | Ý nghĩa có thể có | `bool(value)` |
| --- | --- | --- | --- |
| `0` | `{"stock": 0}` | Sản phẩm tồn tại nhưng hết hàng | `False` |
| `0.0` | `{"discount": 0.0}` | Giảm giá bằng 0% | `False` |
| `False` | `{"enabled": False}` | Tính năng bị tắt | `False` |
| `""` | `{"nickname": ""}` | Người dùng để trống tên gọi | `False` |
| `[]` | `{"courses": []}` | Học viên chưa đăng ký khóa học | `False` |
| `{}` | `{"metadata": {}}` | Đối tượng chưa có thuộc tính mở rộng | `False` |
| `None` | `{"checked_at": None}` | Chưa có thời điểm kiểm kê | `False` |

Những cách diễn giải trên là **ví dụ về quy tắc nghiệp vụ**, không phải ý nghĩa mặc định của Python. Bên cạnh đó, một map có thể chứa chính giá trị `None` trong khi khóa vẫn hiện diện.

## 2. Vì sao kiểm tra theo tính đúng/sai dễ gây lỗi?

Python quy đổi nhiều giá trị như `0`, `False`, `""`, `[]` và `None` thành `False` khi dùng trong điều kiện `if`. Vì vậy, đoạn mã sau không kiểm tra chính xác sự hiện diện:

```python
stock = {"SP01": 0, "SP02": 10}

# SAI khi mục tiêu là kiểm tra mã sản phẩm tồn tại
if stock.get("SP01"):
    print("Sản phẩm đã được đăng ký")
else:
    print("Không tìm thấy sản phẩm")  # Nhánh này chạy, dù SP01 có mặt
```

Lỗi tương tự xuất hiện khi lấy giá trị mặc định bằng toán tử `or`:

```python
config = {"notifications": False, "retry_limit": 0}

notifications = config.get("notifications") or True
retry_limit = config.get("retry_limit") or 3

print(notifications)  # True: đã vô tình bật lại thông báo
print(retry_limit)    # 3: đã vô tình thay số 0 hợp lệ
```

Trong hai phép gán trên, `or` hoạt động dựa trên **truthiness** của giá trị, không dựa trên sự tồn tại của khóa. Nếu chỉ muốn dùng mặc định **khi thiếu khóa**, hãy viết:

```python
notifications = config.get("notifications", True)
retry_limit = config.get("retry_limit", 3)

print(notifications)  # False
print(retry_limit)    # 0
```

Một lưu ý khác: phép kiểm tra `value is None` chỉ trả lời **giá trị có phải `None` hay không**, không trả lời khóa đã tồn tại hay chưa. Khi `None` là giá trị hợp lệ, không thể dùng `is None` thay cho kiểm tra thành viên.

## 3. Cách 1: kiểm tra khóa bằng toán tử `in`

Khi yêu cầu là kiểm tra khóa có tồn tại, cách rõ nhất trong Python là `key in mapping`:

```python
profile = {
    "name": "",
    "age": 0,
    "verified": False,
    "avatar": None,
}

for key in ("name", "age", "verified", "avatar", "email"):
    if key in profile:
        print(key, "có mặt với giá trị", repr(profile[key]))
    else:
        print(key, "không tồn tại")
```

Kết quả là bốn khóa đầu **có mặt**; riêng `email` **không tồn tại**. Trong nhánh đã xác nhận có khóa, việc truy cập `profile[key]` sẽ lấy đúng giá trị, kể cả `None` hay chuỗi rỗng.

Có thể viết hàm trả về cả trạng thái lẫn giá trị:

```python
def lookup(mapping, key):
    if key in mapping:
        return True, mapping[key]
    return False, None

found, value = lookup({"A": None}, "A")
print(found, value)  # True None

found, value = lookup({"A": None}, "B")
print(found, value)  # False None
```

Bộ đôi `(found, value)` giữ được thông tin hiện diện. Khi `found` là `False`, chương trình không sử dụng `value` như một giá trị thực. Một API tương tự trong các ngôn ngữ khác có thể trả kiểu `Option`, `Maybe` hoặc kết quả có nhãn `Found/NotFound`.

### Không nhầm kiểm tra khóa với kiểm tra giá trị

```python
students = {"SV01": None, "SV02": 0}

print("SV01" in students)            # True: kiểm tra khóa
print(None in students.values())     # True: kiểm tra giá trị
print("SV99" in students)            # False
```

Kiểm tra trong `mapping.values()` thường phải duyệt các giá trị, có thể tốn `O(n)`. Còn `key in dict` tra cứu theo khóa bằng cấu trúc băm, thông thường tốn `O(1)` trung bình khi các giả định về băm được thỏa mãn.

## 4. Cách 2: dùng giá trị đánh dấu riêng (sentinel)

Nếu muốn tra cứu bằng **một lời gọi** mà vẫn phân biệt giá trị `None` hợp lệ với khóa vắng mặt, có thể tạo một đối tượng đánh dấu độc nhất:

```python
MISSING = object()

responses = {
    "job-1": None,
    "job-2": False,
    "job-3": "",
}

for job_id in ("job-1", "job-2", "job-3", "job-9"):
    value = responses.get(job_id, MISSING)
    if value is MISSING:
        print(job_id, "không tồn tại")
    else:
        print(job_id, "có mặt:", repr(value))
```

Giải thích:

- `dict.get(key, default)` trả **giá trị thực của khóa** nếu có, kể cả `None`.
- Chỉ khi khóa thiếu, `get` mới trả đối tượng `MISSING`.
- Toán tử `is` kiểm tra **định danh đối tượng**, nên phân biệt sentinel riêng này với các giá trị thông thường.

Sentinel chỉ an toàn khi được dùng như một giá trị đánh dấu **không bao giờ được lưu vào map như dữ liệu hợp lệ**. Thực tế thường tạo sentinel riêng ở phạm vi module hoặc hàm và giữ nó không bị lộ vào dữ liệu đầu vào.

Không nên chọn một giá trị như `-1` hoặc `""` làm sentinel nếu miền giá trị nghiệp vụ có thể chứa giá trị đó. Ví dụ số dư tài khoản có thể âm, và chuỗi rỗng có thể là nội dung hợp lệ.

### Khi nào nên chọn từng cách?

| Nhu cầu | Cách nên dùng |
| --- | --- |
| Chỉ hỏi có khóa hay không | `key in mapping` |
| Khóa có thể thiếu và giá trị mặc định hợp lệ | `mapping.get(key, default)` |
| Cần phân biệt thiếu khóa và `None` | `key in mapping`, sentinel hoặc kết quả có nhãn |
| Muốn gặp lỗi ngay nếu khóa thiếu | `mapping[key]` và xử lý `KeyError` khi cần |
| Muốn thêm giá trị mặc định **vào map** nếu thiếu | `setdefault` hoặc API chèn có điều kiện, với chú ý về tác dụng phụ |

## 5. Đọc dữ liệu và ghi dữ liệu là hai hành vi khác nhau

Một số API có vẻ giống “lấy giá trị mặc định”, nhưng chỉ một số thực sự thay đổi map.

```python
scores = {"SV01": 0}

a = scores.get("SV02", 10)
print(a)       # 10
print(scores)  # {'SV01': 0} — không thêm SV02

b = scores.setdefault("SV02", 10)
print(b)       # 10
print(scores)  # {'SV01': 0, 'SV02': 10} — đã thêm SV02

c = scores.setdefault("SV01", 99)
print(c)       # 0: giữ giá trị hợp lệ đang có
print(scores)  # {'SV01': 0, 'SV02': 10}
```

Đặc biệt, `collections.defaultdict` trong Python có thể **tự sinh giá trị mới khi đọc khóa thiếu qua cú pháp `d[key]`**:

```python
from collections import defaultdict

groups = defaultdict(list)
print(len(groups))     # 0

print(groups["SV99"])  # []: tạo mục mới
print(len(groups))     # 1

print(groups.get("SV88"))  # None: không kích hoạt factory
print(len(groups))         # 1
```

Do đó, “tra cứu không làm thay đổi cấu trúc” là ngữ nghĩa của **phép tra cứu thuần túy**, còn API tạo giá trị theo yêu cầu là một thao tác kết hợp đọc và thêm. Khi thuật toán cần đếm chính xác số khóa hiện có, phải hiểu rõ phương thức đang sử dụng.

### Xóa mà vẫn phân biệt khóa không tồn tại

`dict.pop(key, default)` cũng có vấn đề tương tự nếu `default` trùng với giá trị hợp lệ:

```python
MISSING = object()
data = {"first": None}

removed = data.pop("first", MISSING)
print(removed is MISSING)  # False: đã xóa khóa có giá trị None

removed = data.pop("second", MISSING)
print(removed is MISSING)  # True: khóa không tồn tại
```

Điều này quan trọng khi một API xóa cần trả về hai trạng thái riêng: **“đã xóa”** và **“không có gì để xóa”**. Nếu chỉ cần xóa an toàn và không quan tâm mục có tồn tại không, có thể dùng `data.pop(key, None)`, nhưng phải hiểu là kết quả trả về sẽ không phân biệt hai tình huống.

## 6. Thiết kế kết quả tra cứu rõ ràng hơn

Ở ranh giới giữa các lớp ứng dụng, một kết quả có nhãn thường dễ sử dụng và ít nhầm lẫn hơn một giá trị mặc định. Ví dụ cho một ứng dụng kiểm kê: số lượng có thể là số nguyên không âm, còn `None` biểu diễn “chưa kiểm kê”.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class LookupResult:
    found: bool
    quantity: int | None = None

def find_stock(stock: dict[str, int | None], sku: str) -> LookupResult:
    if sku not in stock:
        return LookupResult(found=False)
    return LookupResult(found=True, quantity=stock[sku])

stock = {
    "SP01": 0,     # Hết hàng
    "SP02": None,  # Chưa kiểm kê
    "SP03": 7,     # Còn hàng
}

for sku in ("SP01", "SP02", "SP03", "SP99"):
    result = find_stock(stock, sku)
    if not result.found:
        print(sku, "chưa có trong danh mục")
    elif result.quantity is None:
        print(sku, "chưa được kiểm kê")
    elif result.quantity == 0:
        print(sku, "đã hết hàng")
    else:
        print(sku, "còn", result.quantity, "đơn vị")
```

Kết quả ở đây có **bốn trường hợp nghiệp vụ**: không có mã, có mã nhưng chưa kiểm kê, có mã với tồn kho bằng 0, và có mã với tồn kho dương. Cách trình bày có nhãn giúp người gọi không phải tự suy đoán dựa trên một giá trị “rỗng”.

Trong ngôn ngữ có kiểu `Option` hay `Maybe`, có thể thể hiện sự phân biệt bằng kết quả lồng nhau khi `null/None` là giá trị hợp lệ: ví dụ trạng thái tương đương `Some(None)` nghĩa là **khóa tồn tại nhưng chưa có giá trị**, còn `None` ở lớp ngoài nghĩa là **không tìm thấy khóa**. Cách đặt tên và kiểu cụ thể tùy ngôn ngữ.

## 7. Tình huống thực tế: phân lớp cấu hình mặc định và cấu hình người dùng

Giả sử ứng dụng có cấu hình mặc định, nhưng người dùng có thể ghi đè một số giá trị:

```python
defaults = {
    "dark_mode": True,
    "max_retries": 3,
    "display_name": "Khách",
}

user_settings = {
    "dark_mode": False,
    "max_retries": 0,
    "display_name": "",
}
```

Đoạn mã sau là **sai** nếu ý nghĩa là chỉ dùng mặc định khi người dùng chưa cấu hình:

```python
def wrong_setting(key):
    return user_settings.get(key) or defaults[key]

print(wrong_setting("dark_mode"))     # True (sai)
print(wrong_setting("max_retries"))   # 3 (sai)
print(wrong_setting("display_name"))  # 'Khách' (sai)
```

Cách đúng là kiểm tra hiện diện:

```python
def setting(key):
    if key in user_settings:
        return user_settings[key]
    return defaults[key]

print(setting("dark_mode"))     # False
print(setting("max_retries"))   # 0
print(repr(setting("display_name")))  # ''
```

Nếu mặc định có thể không chứa khóa, nên quy định rõ cách xử lý khi cả hai nơi đều thiếu: báo lỗi, trả một kết quả `NOT_FOUND` hoặc dùng giá trị dự phòng có chủ đích.

Về mặt thiết kế, thứ tự ưu tiên của nhiều lớp cấu hình có thể là:

```text
cấu hình người dùng (nếu tồn tại khóa)
    ↓ nếu thiếu
cấu hình tổ chức (nếu tồn tại khóa)
    ↓ nếu thiếu
cấu hình mặc định của ứng dụng
    ↓ nếu thiếu
NOT_FOUND / lỗi cấu hình
```

Mỗi bước phải dùng phép kiểm tra **thiếu khóa**, chứ không kiểm tra giá trị có truthy hay không.

## 8. Ngữ nghĩa khác nhau giữa các ngôn ngữ và thư viện

**Python `dict`**: `d.get(k)` trả `None` khi khóa thiếu nếu không cung cấp mặc định; `d[k]` phát sinh `KeyError`; `k in d` kiểm tra hiện diện. `dict` cho phép khóa có giá trị `None`.

**JavaScript `Map`**: `map.get(k)` trả `undefined` khi không có khóa, nhưng một khóa **có thể được gắn với chính giá trị `undefined`**. Vì vậy cần `map.has(k)`:

```javascript
const jobs = new Map();
jobs.set("job-1", undefined);
jobs.set("job-2", null);
jobs.set("job-3", false);

console.log(jobs.get("job-1")); // undefined
console.log(jobs.get("missing")); // undefined
console.log(jobs.has("job-1")); // true
console.log(jobs.has("missing")); // false
```

Với đối tượng JavaScript thông thường, `Object.hasOwn(object, key)` kiểm tra thuộc tính **sở hữu trực tiếp**, tránh nhầm với thuộc tính được kế thừa qua prototype. Cần chọn API phù hợp với `Map` hay object, vì chúng có quy tắc khóa và khả năng kế thừa khác nhau.

**Java `Map`**: `get(key)` thường trả `null` khi không có ánh xạ; một số hiện thực như `HashMap` cho phép giá trị `null`, nên phải gọi `containsKey(key)` nếu cần phân biệt. Một số hiện thực khác, như `ConcurrentHashMap`, không cho phép `null` làm khóa hoặc giá trị. **Hợp đồng giá trị hợp lệ phụ thuộc vào hiện thực**, nên không thể áp dụng máy móc một quy tắc cho mọi map.

Trong cơ sở dữ liệu cũng có khác biệt giữa **không tìm thấy dòng** và **tìm thấy dòng với một cột `NULL`**. Dù có liên hệ về ý nghĩa, thao tác và kiểu kết quả trong SQL phụ thuộc truy vấn, nên khi đưa dữ liệu vào map phải giữ lại thông tin có bản ghi hay không.

## 9. Độ phức tạp và đánh đổi

Gọi `n` là số khóa phân biệt. Các thao tác dưới đây sử dụng Python `dict` làm ví dụ của hash map:

| Thao tác | Ý nghĩa | Thời gian trung bình |
| --- | --- | --- |
| `key in d` | Kiểm tra khóa hiện diện | `O(1)` |
| `d[key]` | Lấy giá trị, báo lỗi nếu thiếu | `O(1)` |
| `d.get(key, default)` | Lấy giá trị hoặc mặc định | `O(1)` |
| `d.setdefault(key, value)` | Lấy hoặc chèn mặc định | `O(1)` |
| `d.pop(key, sentinel)` | Xóa và trả giá trị hoặc sentinel | `O(1)` |
| `value in d.values()` | Kiểm tra sự hiện diện của giá trị | `O(n)` |

Các mốc `O(1)` là **trung bình/kỳ vọng**, giả định băm và so sánh khóa có chi phí cơ bản hằng số, hash phân bố hợp lý và bảng được quản lý tải. Nhiều va chạm có thể làm chi phí tăng; một lần mở rộng bảng có thể tốn `O(n)`. Với map dựa trên cây tìm kiếm cân bằng, kiểm tra khóa, lấy, chèn và xóa thường có giới hạn `O(log n)`.

Kiểm tra `key in d` rồi đọc `d[key]` thực hiện hai lần tra cứu, nhưng vẫn là `O(1)` trung bình xét theo độ phức tạp tiệm cận. Sentinel dùng `get` có thể gộp về một lượt tra cứu khi cần cả giá trị và trạng thái có mặt. Trong ứng dụng thông thường, **tính rõ ràng và đúng nghĩa nghiệp vụ** quan trọng hơn chênh lệch nhỏ này.

Kiểm tra và trả về giá trị bằng sentinel chỉ cần thêm `O(1)` bộ nhớ cho đối tượng đánh dấu; một kết quả `(found, value)` cũng thêm `O(1)` bộ nhớ cho mỗi kết quả. Bộ nhớ lưu map nhìn chung phụ thuộc hiện thực, với hash map và tree map thường là `O(n)` cho các mục và cấu trúc phụ trợ.

## 10. Checklist kiểm tra hợp đồng tra cứu

Khi thiết kế hoặc đánh giá một API dùng map, nên trả lời được:

1. **Giá trị hợp lệ gồm những gì?** `None`/`null`, `0`, `False`, chuỗi và collection rỗng có được lưu không?
2. **Làm sao biểu diễn khóa không tồn tại?** Ngoại lệ, cờ `found`, sentinel hay một kiểu kết quả có nhãn?
3. **Đọc khóa thiếu có tạo mục mới không?** `get` trên `dict` không tạo, nhưng truy cập chỉ số của `defaultdict` có thể tạo.
4. **Có cần phân biệt “không tồn tại”, “chưa biết”, “không có dữ liệu” và “giá trị bằng 0” không?** Nếu có, cần mã hóa rõ từng trạng thái.
5. **Hành vi xóa/ghi đè có giữ được khả năng báo “không tìm thấy” không?** Các API như `pop` và `put` có thể mang nhiều ngữ nghĩa tùy hiện thực.

Không nên chọn một sentinel tình cờ nằm trong miền dữ liệu có thể hợp lệ. Với API công khai, nên mô tả rõ từng trạng thái trong kiểu trả về, tài liệu và kiểm thử.

## 11. Tự luyện tập

**Bài 1.** Cho `d = {"A": 0, "B": None, "C": False, "D": ""}`. Những khóa nào có mặt? Vì sao `if d.get("A")` trả nhánh sai?

**Bài 2.** Phân tích kết quả của `d.get("B")` và `d.get("Z")`. Viết hai cách phân biệt hai tình huống này trong Python.

**Bài 3.** Trong bảng cấu hình, người dùng đặt `retry_limit = 0` để tắt chức năng thử lại. Vì sao `config.get("retry_limit") or 5` là cách lấy mặc định không đúng? Viết cách sửa.

**Bài 4.** Một chương trình dùng `defaultdict(list)`. Tại sao chỉ đọc `d["missing"]` lại có thể thay đổi `len(d)`? Nếu cần đọc mà không tạo mục, nên làm gì?

**Bài 5.** Dùng `dict.pop` để xóa một khóa và phân biệt “đã xóa khóa có giá trị `None`” với “khóa không tồn tại”.

**Bài 6.** Thiết kế kiểu kết quả cho một hệ thống thư viện, trong đó tra mã sách có thể gặp: sách không có trong danh mục, sách đã đăng ký nhưng chưa nhập số lượng, sách có số bản bằng 0 và sách có số bản lớn hơn 0.

<details>
<summary>Đáp án tham khảo</summary>

1. Cả `A`, `B`, `C`, `D` đều có mặt. `d.get("A")` trả `0`, là giá trị falsy, dù khóa tồn tại.
2. Cả hai lời gọi `get` đều trả `None`. Dùng `"B" in d` so với `"Z" in d`, hoặc `d.get(k, MISSING) is MISSING` với sentinel riêng.
3. `or 5` thay cả giá trị hợp lệ `0`; dùng `config.get("retry_limit", 5)` để chỉ dùng `5` khi khóa thiếu.
4. `d["missing"]` gọi factory để tạo list và lưu vào map. Dùng `d.get("missing")` hoặc kiểm tra `"missing" in d` khi không muốn tự thêm.
5. Dùng `MISSING = object()`; kiểm tra `removed = d.pop(k, MISSING)` và `removed is MISSING`.
6. Có thể dùng kết quả `(found, quantity)` với `found = False` cho mã thiếu; `(True, None)` cho chưa nhập số lượng; `(True, 0)` cho hết sách; `(True, n)` với `n > 0` cho sách còn bản.

</details>

## Ghi nhớ

**Khóa không tồn tại** và **khóa có giá trị rỗng hợp lệ** là hai trạng thái riêng. Việc một giá trị là `0`, `False`, `""`, `[]` hay `None` không có nghĩa khóa bị thiếu. Hãy kiểm tra sự hiện diện bằng `key in map` hoặc một sentinel/kiểu kết quả có nhãn; chỉ sử dụng giá trị mặc định khi hợp đồng nghiệp vụ cho phép. Tách rõ **trạng thái tìm thấy** khỏi **nội dung giá trị** giúp thao tác tra cứu, cập nhật, xóa và lựa chọn cấu trúc dữ liệu đúng ngay cả ở những tình huống biên.
