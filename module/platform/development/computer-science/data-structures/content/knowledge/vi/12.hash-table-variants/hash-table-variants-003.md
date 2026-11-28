# Băm hoàn hảo tối thiểu và đánh đổi khi tập khóa thay đổi

Khi thiết kế từ điển (*dictionary*) hoặc tập hợp (*set*) bằng bảng băm, ta thường muốn tìm khóa nhanh và tiết kiệm bộ nhớ. Với một **tập khóa cố định**, băm hoàn hảo có thể loại bỏ va chạm giữa các khóa đã lưu. **Băm hoàn hảo tối thiểu** (*minimal perfect hashing*, viết tắt **MPH**) còn đưa đúng \(n\) khóa vào **đúng \(n\) chỉ số khác nhau**.

Nếu tập khóa thay đổi liên tục, việc duy trì tính hoàn hảo và tối thiểu có thể làm tăng chi phí chèn, xóa và xây dựng lại. Bài học trong chương **Biến thể bảng băm** thuộc nền tảng cấu trúc dữ liệu này giải thích bất biến của MPH, cách tra cứu, chi phí thời gian và bộ nhớ, cùng những lựa chọn khi tập khóa không còn tĩnh.

## 1. Định nghĩa băm hoàn hảo tối thiểu

Cho tập \(S=\{k_1,k_2,\ldots,k_n\}\) gồm \(n>0\) **khóa phân biệt**. Hàm băm \(h\) được gọi là **hoàn hảo** trên \(S\) nếu:

\[
\forall x,y\in S,\quad x\neq y\Rightarrow h(x)\neq h(y).
\]

Hàm \(h\) được gọi là **hoàn hảo tối thiểu** trên \(S\) nếu còn thỏa điều kiện ánh xạ **song ánh** lên chính xác \(n\) chỉ số:

\[
\boxed{h:S\longrightarrow\{0,1,\ldots,n-1\},\quad h\text{ là song ánh}.}
\]

Nghĩa là trong tập khóa đã lưu, mỗi chỉ số từ 0 đến \(n-1\) đều được sử dụng **đúng một lần**.

| Loại băm | Bảo đảm trên tập khóa \(S\) | Miền địa chỉ |
| --- | --- | --- |
| Băm thông thường | Có thể có va chạm | Tùy bảng |
| **Băm hoàn hảo** (*perfect hash*) | Không va chạm giữa các khóa trong \(S\) | Có thể nhiều hơn \(n\) |
| **Băm hoàn hảo tối thiểu** (*minimal perfect hash*) | Không va chạm và dùng đủ mọi địa chỉ | Đúng \(n\) địa chỉ |

**Tối thiểu** nói về số chỉ số đầu ra dành cho tập khóa, không có nghĩa hàm chỉ chiếm \(n\) byte bộ nhớ. **Hoàn hảo** nói về tập \(S\), không phải mọi khóa có thể được hỏi sau này.

### Ví dụ năm khóa

Xét:

\[
S=\{11,17,23,34,40\},\qquad n=5.
\]

Hàm \(h(k)=k\bmod 5\) cho kết quả:

| Khóa | \(h(k)\) | Chỉ số |
| ---: | ---: | ---: |
| 11 | 1 | 1 |
| 17 | 2 | 2 |
| 23 | 3 | 3 |
| 34 | 4 | 4 |
| 40 | 0 | 0 |

Các khóa trong \(S\) lần lượt dùng đủ các chỉ số \(0,1,2,3,4\) mà không trùng nhau. Như vậy, \(h\) là MPH **trên tập cụ thể này**.

~~~text
Chỉ số:     0      1      2      3      4
Khóa:     [40]   [11]   [17]   [23]   [34]

h(23) = 3  → ô 3 chứa 23 → tìm thấy
h(13) = 3  → ô 3 chứa 23 → 13 không thuộc S
~~~

Khóa 13 không thuộc \(S\) nhưng vẫn được đưa đến ô hợp lệ. Vì vậy, **MPH không tự thực hiện kiểm tra thành viên tập hợp**.

## 2. Các bất biến và cách xác minh khóa

Một bảng tra cứu tĩnh sử dụng MPH thường chứa:

1. **Mô tả hàm MPH**: seed, tham số, mảng độ dời hoặc cấu trúc hỗ trợ để tính chỉ số.
2. **Mảng giá trị có \(n\) vị trí**: giá trị gắn với \(k\) nằm ở vị trí \(h(k)\).
3. **Thông tin xác minh thành viên**, nếu người gọi được phép truy vấn khóa ngoài \(S\).

Giả sử mỗi khóa trong ví dụ gắn với một giá trị:

~~~text
values[0] = giá trị của khóa 40
values[1] = giá trị của khóa 11
values[2] = giá trị của khóa 17
values[3] = giá trị của khóa 23
values[4] = giá trị của khóa 34
~~~

Nếu hàm \(h\) được tính trong số bước hằng số, việc lấy giá trị trong mảng có độ phức tạp \(O(1)\). Nhiều thuật toán MPH thực tế được thiết kế để truy vấn bằng số phép băm và truy cập bộ nhớ cố định. Tuy nhiên, **định nghĩa MPH chỉ bảo đảm tính song ánh trên \(S\)**; tự nó không bắt buộc mọi biểu diễn MPH đều có chi phí truy vấn \(O(1)\).

Để tra cứu **chính xác** khi khóa có thể không tồn tại, phải xác minh khóa ở địa chỉ ứng viên. Có thể lưu khóa gốc cạnh giá trị, tra cứu qua một nguồn xác thực khác hoặc dùng giải pháp hỗ trợ kiểm tra thành viên chính xác.

| Cách sử dụng | Yêu cầu |
| --- | --- |
| Người gọi luôn truyền khóa thuộc tập \(S\) theo hợp đồng API | Có thể truy cập trực tiếp theo \(h(k)\) |
| Người gọi có thể truyền khóa ngoài \(S\) và phải trả lời đúng tuyệt đối | Cần xác minh khóa thật, không chỉ kiểm tra địa chỉ |
| Chỉ lưu dấu vân tay (*fingerprint*) ngắn | Có thể có dương tính giả; cần chấp nhận sai số hoặc bổ sung xác minh |

Ví dụ, nếu dùng fingerprint \(f\) bit, đồng thời giả định các dấu vân tay độc lập và phân bố đều, một khóa lạ có xác suất vượt qua kiểm tra fingerprint khoảng \(2^{-f}\). Với \(f=16\), mức lý tưởng là \(1/65536\) cho **một lần kiểm tra**. Đây không phải bảo đảm không sai, nhất là nếu đầu vào được cố tình chọn để gây trùng dấu vân tay.

**Bất biến quan trọng:** với mọi \(k\in S\), giá trị được đặt đúng vị trí \(h(k)\); hàm MPH và cách bố trí giá trị phải luôn tương thích. Đổi hàm mà không sắp lại mảng sẽ gây trả kết quả sai.

## 3. Quy trình xây dựng MPH từ tập khóa tĩnh

MPH thường được xây dựng **ngoại tuyến** (*offline*) từ toàn bộ tập khóa đã biết. Một quy trình tổng quát gồm:

1. Chuẩn hóa biểu diễn khóa; loại bản sao trùng để thu được \(n\) khóa phân biệt.
2. Chọn thuật toán xây dựng và các tham số băm ban đầu.
3. Phân bố khóa vào cấu trúc trung gian; thử thay đổi tham số, độ dời hoặc thứ tự xử lý để loại va chạm ở vị trí cuối.
4. Xác nhận có đúng \(n\) địa chỉ khác nhau, tất cả nằm trong \(0,\ldots,n-1\).
5. Xếp các giá trị theo vị trí cuối của MPH, rồi lưu mô tả hàm và dữ liệu.

~~~mermaid
flowchart TD
    A[Tập khóa S] --> B[Chuẩn hóa và loại khóa trùng]
    B --> C[Xây dựng cấu trúc MPH]
    C --> D{Các vị trí đã duy nhất và đủ 0..n-1?}
    D -->|Chưa| E[Thử tham số hoặc cách sắp khác]
    E --> C
    D -->|Đúng| F[Xếp giá trị theo chỉ số MPH]
    F --> G[Lưu snapshot tĩnh]
~~~

Một số thuật toán tìm **độ dời** cho từng nhóm khóa; một số biểu diễn quan hệ giữa khóa và ô bằng **đồ thị hoặc siêu đồ thị**, sau đó giải cấu trúc để tạo địa chỉ duy nhất. Các hướng thường được nhắc đến gồm **CHD** (*compress, hash and displace*) và **BDZ** (xây dựng dựa trên siêu đồ thị).

Chi phí xây dựng, bộ nhớ cho mô tả hàm và tốc độ tra cứu phụ thuộc thuật toán cụ thể. Không thể khẳng định **mọi** cách xây dựng MPH đều có cùng một độ phức tạp.

### So sánh với bảng băm hoàn hảo hai tầng FKS

Phương pháp **FKS** (*Fredman–Komlós–Szemerédi*) tạo bảng băm hoàn hảo cho tập khóa tĩnh bằng hai tầng. Tầng đầu phân nhóm; nếu nhóm \(i\) chứa \(b_i\) khóa, tầng hai có thể cấp \(b_i^2\) ô để dễ tìm hàm không va chạm cho nhóm.

Một thiết kế FKS điển hình có thể đạt bộ nhớ \(O(n)\), xây dựng \(O(n)\) theo kỳ vọng và tra cứu \(O(1)\) trong trường hợp xấu nhất theo mô hình phép băm hằng số. **Nhưng tổng các ô phụ có thể lớn hơn \(n\)**, nên FKS như vậy **không tự động là MPH**. MPH yêu cầu thêm rằng các chỉ số cuối **chính xác** là \(0,\ldots,n-1\), không có vị trí thừa trong miền đầu ra.

## 4. MPH tiết kiệm bộ nhớ ở đâu?

Với \(n\) khóa, MPH cho phép xếp **đúng \(n\) giá trị hoặc offset** vào đúng \(n\) vị trí mảng, không phải giữ ô giá trị trống nhằm giải quyết va chạm giữa khóa thuộc \(S\).

Tuy nhiên, một giải pháp hoàn chỉnh vẫn có thể tốn bộ nhớ cho:

- Cấu trúc mô tả MPH: seed, bảng phụ, độ dời, các bit điều khiển hoặc dữ liệu hỗ trợ.
- Mảng \(n\) giá trị hoặc \(n\) con trỏ/offset.
- Khóa gốc hoặc phương tiện xác minh thành viên nếu cần trả lời chính xác đối với khóa lạ.
- Chi phí căn chỉnh, cấp phát và dữ liệu ứng dụng khác.

Những thuật toán MPH nén có thể chỉ dùng **vài bit metadata trên mỗi khóa**, nhưng mức cụ thể phụ thuộc thuật toán và cấu hình. Không nên lấy số bit này thay cho tổng bộ nhớ chứa cả khóa, giá trị và thông tin xác minh.

| Cách tổ chức | Thành phần chính | Đánh đổi |
| --- | --- | --- |
| Bảng băm động | Mảng có dung lượng dự phòng, khóa, giá trị và metadata xử lý va chạm | Dễ thêm/xóa, nhưng cần kiểm soát hệ số tải |
| MPH tĩnh | Mô tả MPH, mảng giá trị đúng \(n\) vị trí, xác minh khóa nếu cần | Không có ô dư trong mảng giá trị; phải trả chi phí xây dựng trước |

Việc xếp giá trị trong mảng liên tục cũng có thể cải thiện tính cục bộ bộ nhớ, nhưng lợi ích thực tế phụ thuộc cấu trúc giá trị, phần cứng và workload. Cần đo thay vì mặc định MPH luôn nhanh hơn mọi bảng băm động.

## 5. Thêm, xóa và cập nhật khác nhau thế nào?

Tính tối thiểu gắn với **tập khóa cụ thể \(S\)** và **số khóa \(n\)**.

### Thêm khóa mới

Trong ví dụ \(S=\{11,17,23,34,40\}\), hàm \(h(k)=k\bmod5\) dùng trọn năm chỉ số. Thêm khóa 13 khiến \(h(13)=3=h(23)\): hàm không còn hoàn hảo trên tập mới.

Hơn nữa, tập mới có **sáu khóa**, nên một MPH cho tập mới phải ánh xạ lên **sáu chỉ số** \(0,\ldots,5\). Hàm cũ chỉ trả về năm chỉ số thì không thể chứa sáu khóa phân biệt mà không va chạm.

### Xóa khóa

Nếu xóa 23 khỏi tập ban đầu, chỉ số 3 không còn được dùng. Hàm cũ vẫn có thể **không va chạm giữa bốn khóa còn lại**, nhưng bảng với năm địa chỉ đã **không còn tối thiểu** đối với tập bốn khóa.

Để lấy lại tính tối thiểu, có thể xây MPH mới trên bốn khóa, với các chỉ số \(0,\ldots,3\). Việc này có thể thay đổi vị trí của nhiều giá trị đã lưu.

### Chỉ sửa giá trị

Nếu khóa 23 vẫn tồn tại nhưng giá trị liên kết đổi từ C thành C2, hàm MPH và tập khóa **không đổi**. Ta có thể cập nhật giá trị tại chỉ số \(h(23)=3\) mà không phải xây lại hàm.

| Thao tác | MPH cũ có thể giữ nguyên không? | Ghi chú |
| --- | --- | --- |
| Tra cứu khóa đã lưu | Có | Đọc đúng vị trí và xác minh khi cần |
| Đổi giá trị của khóa hiện có | Có | Sửa giá trị, không sửa tập khóa |
| Thêm khóa mới | Không thể bảo đảm hoàn hảo/tối thiểu trên tập mới | Cần cơ chế bổ sung hoặc tái xây dựng |
| Xóa khóa | Có thể giữ địa chỉ cũ cho khóa còn lại, nhưng mất tính tối thiểu | Dùng dấu xóa hoặc tái xây dựng |
| Đổi định danh khóa | Tương đương xóa khóa cũ và thêm khóa mới | Phải tính lại cách bố trí liên quan |

**Điểm cốt lõi:** cập nhật **giá trị gắn với khóa** thường rẻ; thay đổi **chính tập khóa** mới gây áp lực lên bất biến MPH.

## 6. Chiến lược lai: MPH nền + bảng cập nhật + dấu xóa

Nếu phần lớn dữ liệu tĩnh nhưng đôi lúc thêm hoặc xóa khóa, có thể kết hợp:

- **Base:** một snapshot chỉ đọc dùng MPH trên tập \(S_0\).
- **Delta:** một bảng băm động lưu khóa mới hoặc giá trị cập nhật.
- **Tombstone:** tập dấu xóa cho khóa đã thuộc base nhưng hiện không còn hiệu lực.

~~~mermaid
flowchart TD
    A[Tra cứu k] --> B{Delta có k?}
    B -->|Có| C[Trả giá trị trong delta]
    B -->|Không| D{Tombstone có k?}
    D -->|Có| E[Không tìm thấy]
    D -->|Không| F[Tra vị trí qua MPH của base]
    F --> G{Khóa ở vị trí có đúng là k?}
    G -->|Có| H[Trả giá trị base]
    G -->|Không| E
~~~

**Thứ tự tra cứu rất quan trọng:** xem **delta** trước để lấy giá trị mới, rồi kiểm tra **tombstone** để loại khóa đã xóa, cuối cùng mới truy vấn **base**. Nếu đọc base trước, một cập nhật hoặc xóa có thể bị bỏ qua.

Các bất biến cần giữ:

1. MPH nền chỉ cần hoàn hảo tối thiểu trên **tập khóa ở thời điểm snapshot \(S_0\)**.
2. Delta lưu thay đổi hiện hành và có quyền **ghi đè giá trị cũ** trong base.
3. Tombstone chặn dữ liệu base đã bị xóa; thêm lại khóa phải xóa dấu tombstone.
4. Khóa ngoài \(S_0\) vẫn phải xác minh trước khi trả dữ liệu từ base.

Thiết kế này **không còn là một MPH duy nhất trên toàn bộ tập khóa hiện hành**. Nó tận dụng MPH cho phần ổn định và dùng bảng băm động cho phần thay đổi.

Do delta thường là bảng băm động, toàn bộ thao tác tra cứu thường chỉ được bảo đảm **\(O(1)\) trung bình hoặc theo kỳ vọng** với hàm băm và hệ số tải phù hợp. Không được suy ra \(O(1)\) trường hợp xấu nhất cho cả hệ lai chỉ từ MPH ở base.

## 7. Ví dụ Python: giữ MPH tĩnh và cho phép thay đổi khóa

Ví dụ sau dùng chính hàm \(h(k)=k\bmod5\), vốn **đã được chứng minh là MPH trên tập năm khóa ở mục 1**. Lớp Python minh họa cách đọc, thêm, xóa và cập nhật bằng delta/tombstone. **Đây không phải thuật toán tự xây dựng MPH tổng quát** cho một tập khóa bất kỳ.

~~~python
class StaticMphWithDelta:
    def __init__(self):
        # Snapshot ban đầu: base_keys[i] có h(key) == i.
        self.base_keys = [40, 11, 17, 23, 34]
        self.base_values = ["E", "A", "B", "C", "D"]

        self.delta = {}       # Khóa mới hoặc giá trị cập nhật.
        self.deleted = set()  # Khóa thuộc base đã bị xóa.

    def _base_slot(self, key):
        if type(key) is not int:
            raise TypeError("Ví dụ chỉ hỗ trợ khóa nguyên")

        i = key % len(self.base_keys)
        # MPH luôn cho vị trí ứng viên, nhưng phải xác minh khóa.
        return i if self.base_keys[i] == key else None

    def get(self, key, default=None):
        if key in self.delta:
            return self.delta[key]
        if key in self.deleted:
            return default

        i = self._base_slot(key)
        return default if i is None else self.base_values[i]

    def put(self, key, value):
        self._base_slot(key)       # Kiểm tra kiểu khóa.
        self.delta[key] = value
        self.deleted.discard(key)  # Cho phép khôi phục khóa đã xóa.

    def remove(self, key):
        self._base_slot(key)       # Kiểm tra kiểu khóa.
        self.delta.pop(key, None)
        if self._base_slot(key) is not None:
            self.deleted.add(key)  # Chỉ cần dấu xóa nếu khóa có trong base.


index = StaticMphWithDelta()
print(index.get(23))          # C: dữ liệu trong base
print(index.get(13))          # None: 13 không thuộc base

index.put(13, "NEW")          # Thêm khóa mới
index.put(23, "UPDATED")      # Ghi đè giá trị cũ
index.remove(17)              # Xóa khóa trong base

print(index.get(13))          # NEW
print(index.get(23))          # UPDATED
print(index.get(17))          # None

index.put(17, "RESTORED")     # Thêm lại khóa đã xóa
print(index.get(17))          # RESTORED
~~~

Hàm **get** có cách dùng tương tự **dict.get**: trả về giá trị mặc định nếu không tìm thấy. Nếu ứng dụng cho phép lưu giá trị **None** và phải phân biệt nó với khóa vắng mặt, hãy dùng một **sentinel riêng** hoặc API cung cấp cờ tồn tại.

Ví dụ có bốn đặc điểm cần quan sát:

- Khóa 13 có cùng chỉ số base với 23 nhưng truy vấn trước khi thêm vẫn trả về **không tìm thấy** do kiểm tra khóa thật.
- Thêm 13 chỉ thay đổi delta, không sửa hàm MPH của base.
- Sửa 23 được ghi vào delta và luôn được trả về trước giá trị C cũ.
- Xóa 17 phải để lại tombstone trong khi base vẫn còn chứa 17; thêm lại 17 sẽ bỏ dấu xóa.

## 8. Tái xây dựng MPH khi lớp cập nhật lớn dần

Sau nhiều lần thêm/xóa, delta và tombstone có thể làm tăng bộ nhớ, số phép kiểm tra và chi phí quản lý. Ta có thể **hợp nhất theo đợt** bằng một lần xây lại MPH:

1. **Chụp trạng thái nhất quán:** lấy khóa từ base chưa bị tombstone loại bỏ, áp dụng giá trị ghi đè trong delta, rồi thêm các khóa mới.
2. **Xây MPH mới:** dùng tập khóa hiện hành \(S_1\), tạo hàm với đúng \(|S_1|\) chỉ số khác nhau, và xếp các giá trị tương ứng.
3. **Kiểm tra:** mọi khóa trong \(S_1\) có vị trí riêng, không mất giá trị, và các khóa ngoài tập bị từ chối đúng khi ứng dụng yêu cầu.
4. **Chuyển phiên bản:** đưa truy vấn sang snapshot mới, loại các thay đổi đã được hợp nhất khỏi delta/tombstone.

~~~text
Snapshot v1 (MPH) + Delta v1 + Tombstone v1
                    |
             Chụp dữ liệu hiện hành
                    |
           Xây và kiểm tra Snapshot v2
                    |
             Chuyển phiên bản đọc
                    |
           Snapshot v2 + Delta mới
~~~

Khi ứng dụng vẫn nhận cập nhật **trong lúc xây snapshot mới**, cần ghi lại các thay đổi xảy ra **sau thời điểm chụp dữ liệu** và bảo toàn chúng khi chuyển sang phiên bản mới. Các kỹ thuật có thể dùng là **nhật ký cập nhật**, **delta theo số phiên bản** hoặc **chuyển con trỏ snapshot nguyên tử** kết hợp quản lý vòng đời các bản đang được đọc.

Việc chỉ đơn giản xóa delta khi snapshot mới sẵn sàng có thể **làm mất cập nhật vừa phát sinh**. Đây là vấn đề nhất quán dữ liệu độc lập với tính chất MPH.

### Khi nào nên hợp nhất?

Không có ngưỡng chung cho mọi workload. Có thể đo độ trễ và bộ nhớ khi lượng khóa mới/sửa/xóa đạt 10%, 20% hoặc 30% số khóa base. Những tỷ lệ đó chỉ là **mốc khảo sát**; ngưỡng phù hợp phụ thuộc chi phí xây lại, tốc độ phát sinh thay đổi và yêu cầu độ trễ.

Nếu xây MPH đồng bộ trong yêu cầu chèn/xóa, chính yêu cầu đó có thể bị chậm đáng kể. Xây một snapshot mới riêng rồi chuyển phiên bản sẽ linh hoạt hơn cho hệ thống cần phục vụ truy vấn liên tục, nhưng yêu cầu đồng bộ dữ liệu cẩn thận.

## 9. So sánh độ phức tạp và đánh đổi

| Cấu trúc | Tra cứu | Thêm/xóa khóa | Bộ nhớ và xây dựng |
| --- | --- | --- | --- |
| **MPH tĩnh thuần túy** | Thường \(O(1)\) nếu hàm MPH cụ thể có thuật toán truy vấn hằng số | Muốn luôn tối thiểu trên tập mới thì phải xây lại hoặc dùng cơ chế động đặc biệt | Mảng đúng \(n\) giá trị, cộng metadata và xác minh; cần xây dựng trước |
| **MPH + delta/tombstone** | Thường \(O(1)\) trung bình/kỳ vọng do tra delta động | Ghi thay đổi nhỏ vào delta, hợp nhất theo đợt | Có phần bộ nhớ tạm cho delta, dấu xóa và snapshot mới |
| **Bảng băm động** | Thường \(O(1)\) trung bình/kỳ vọng khi băm và tải phù hợp | Thường \(O(1)\) trung bình hoặc phân bổ, có thể tái băm | Dùng dung lượng dự phòng để xử lý va chạm |
| **Cây tìm kiếm cân bằng** | \(O(\log n)\) trường hợp xấu nhất | \(O(\log n)\) trường hợp xấu nhất | Metadata cho nút và con trỏ; hỗ trợ duyệt có thứ tự |
| **Mảng đã sắp xếp** | \(O(\log n)\) với tìm kiếm nhị phân | Có thể \(O(n)\) do phải dịch phần tử | Bố trí gọn, phù hợp dữ liệu ít thay đổi và cần thứ tự |

Các giới hạn tra cứu \(O(1)\) giả định phép băm và so sánh khóa có chi phí hằng số. Với chuỗi dài hoặc số nguyên tùy ý, cần tính thêm thời gian xử lý khóa. Chi phí **xây dựng MPH** không có một công thức chung cho mọi thuật toán; cần đánh giá phương pháp và thư viện cụ thể.

### Cách ước lượng điểm hòa vốn

Nếu một phiên bản dữ liệu có \(q\) lượt tra cứu và \(u\) lần đổi khóa, có thể dùng mô hình chi phí để so sánh:

\[
T_{\mathrm{MPH\ lai}}\approx
T_{\mathrm{build}}+
qT_{\mathrm{lookup}}+
uT_{\mathrm{delta}}+
T_{\mathrm{rebuild}},
\]

trong khi một bảng băm động có thể được mô hình hóa bằng:

\[
T_{\mathrm{dynamic}}\approx
qT'_{\mathrm{lookup}}+
uT'_{\mathrm{update}}.
\]

Đây là **mô hình để đo** trên dữ liệu thực, không phải lời khẳng định mọi cấu trúc đều chạy với những hằng số giống nhau. Khi \(q\) rất lớn và \(u\) rất nhỏ, phí xây dựng ban đầu có thể được bù lại. Khi \(u\) lớn, tái xây dựng MPH và duy trì delta có thể trở thành chi phí chính.

## 10. Tình huống áp dụng

**Bộ từ khóa trình biên dịch:** Từ khóa thường chỉ thay đổi qua phiên bản ngôn ngữ, còn việc tra cứu diễn ra liên tục khi phân tích mã nguồn. Xây MPH lúc đóng gói một phiên bản có thể hợp lý; thêm từ khóa ở phiên bản mới thì tái xây dựng.

**Danh mục mã lỗi tĩnh:** Một tập ID cố định trỏ tới mô tả ngắn. MPH đưa ID tới vị trí tương ứng trong mảng thông báo. Nếu API có thể nhận ID lạ, cần xác minh khóa để tránh trả nhầm thông báo.

**Bảng ánh xạ tài khoản hoạt động:** Tài khoản được tạo, đổi trạng thái và xóa thường xuyên. Chỉ mục MPH thuần tĩnh gây chi phí tái xây dựng lặp lại; bảng băm động hoặc cấu trúc được thiết kế cho ghi thường phù hợp hơn.

**Từ điển gốc và một ít từ bổ sung:** MPH lưu tập từ ổn định; delta lưu từ mới và giá trị cập nhật; tombstone đánh dấu từ đã bị loại. Hợp nhất theo đợt giúp cân bằng tốc độ đọc với tần suất thay đổi.

## 11. Những nhầm lẫn thường gặp

1. **MPH chỉ cần \(n\) byte bộ nhớ.** \(n\) là số **chỉ số đầu ra**; hệ thống còn cần biểu diễn hàm và dữ liệu.
2. **MPH tự xác định khóa có tồn tại hay không.** Khóa ngoài tập vẫn có thể được băm vào một vị trí hợp lệ.
3. **Xóa khóa vẫn giữ tính tối thiểu.** Nếu giữ miền cũ có \(n\) chỉ số cho \(n-1\) khóa thì không còn tối thiểu.
4. **Sửa giá trị luôn phải xây lại MPH.** Tập khóa giữ nguyên thì thường chỉ cần thay giá trị tại đúng chỉ số.
5. **Một MPH dùng được cho mọi tập khóa.** Hàm hoàn hảo trên tập này có thể va chạm trên tập khác.
6. **Thêm delta vẫn giữ \(O(1)\) trường hợp xấu nhất cho tất cả truy vấn.** Không mặc nhiên đúng với lớp bảng băm động.
7. **Đổi MPH nhưng không sắp lại mảng giá trị vẫn an toàn.** Sai: vị trí \(h(k)\) có thể thay đổi.

## 12. Tự kiểm tra

**Câu 1.** Với \(S=\{11,17,23,34,40\}\), vì sao \(h(k)=k\bmod5\) là MPH trên \(S\) nhưng không xác nhận được khóa 13?

**Lời giải:** Năm khóa chiếm đúng năm chỉ số từ 0 đến 4. Nhưng \(h(13)=3=h(23)\); nếu không so sánh khóa trong ô 3 với 13, truy vấn có thể trả kết quả sai.

**Câu 2.** Xóa khóa 17 khỏi \(S\), giữ mảng năm ô và hàm cũ. Tính chất nào còn đúng, tính chất nào mất?

**Lời giải:** Bốn khóa còn lại vẫn không va chạm. Tuy nhiên bảng hiện có năm địa chỉ cho bốn khóa nên không còn là một MPH trên tập hiện hành. Có thể giữ bảng cũ kèm dấu xóa, hoặc xây lại MPH cho bốn khóa.

**Câu 3.** Khóa 23 vẫn còn nhưng giá trị thay đổi từ C thành C2. Có phải xây lại MPH không?

**Lời giải:** Không. Hàm băm và tập khóa không thay đổi; chỉ sửa giá trị ở vị trí \(h(23)=3\).

**Câu 4.** Vì sao phải đọc delta trước base trong thiết kế kết hợp?

**Lời giải:** Delta có thể giữ giá trị mới của một khóa đã có trong base. Đọc base trước sẽ trả giá trị cũ. Tombstone cũng phải được kiểm tra trước base để tránh làm khóa đã xóa xuất hiện lại.

**Câu 5.** Trong lúc xây snapshot v2, hệ thống tiếp nhận thêm một khóa mới. Làm gì để không mất khóa khi chuyển từ v1 sang v2?

**Lời giải:** Ghi nhận thay đổi xảy ra sau thời điểm chụp dữ liệu, áp dụng vào delta của phiên bản mới hoặc phát lại từ nhật ký trước khi hoàn tất chuyển phiên bản. Không xóa những thay đổi chưa được hợp nhất.

## 13. Ghi nhớ

**Băm hoàn hảo tối thiểu (MPH)** ánh xạ \(n\) khóa phân biệt đã biết trước tới **đúng \(n\) chỉ số \(0,\ldots,n-1\)**, mỗi chỉ số được dùng đúng một lần. Nó phù hợp với **tập khóa ổn định, tra cứu thường xuyên** và nhu cầu sắp dữ liệu thành mảng gọn. MPH không tự bảo đảm kiểm tra khóa ngoài tập và không có nghĩa toàn bộ cấu trúc chỉ chiếm \(n\) ô bộ nhớ.

Khi **thêm hoặc xóa khóa**, tính tối thiểu gắn với tập cũ có thể không còn. Có thể **tái xây dựng MPH** hoặc dùng **MPH nền + bảng băm động + tombstone**, sau đó hợp nhất theo đợt. Chọn cấu trúc cần dựa trên cả **độ phức tạp tra cứu, chi phí cập nhật, bộ nhớ thực tế và tần suất tái xây dựng**.
