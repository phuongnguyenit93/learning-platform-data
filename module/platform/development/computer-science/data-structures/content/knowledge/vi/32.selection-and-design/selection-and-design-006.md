# Giữ ổn định danh tính phần tử, tham chiếu và thứ tự duyệt

Trong một hệ thống quản lý công việc, mỗi tác vụ có mã `taskId`. Khi có tác vụ mới, một số phần tử trong mảng có thể đổi vị trí. Khi xóa tác vụ, ô nhớ cũ có thể được dùng lại. Khi lập báo cáo, hệ thống phải hiển thị tác vụ theo thứ tự tạo, dù các tác vụ liên tục được thêm và sửa. Ba yêu cầu tưởng liên quan chặt chẽ này thực ra nói về **ba loại ổn định khác nhau**:

- **Danh tính phần tử:** tác vụ nào là tác vụ nào, kể cả khi vị trí hoặc nội dung của nó thay đổi.
- **Tham chiếu đến phần tử:** cách truy cập tác vụ còn hợp lệ sau các thao tác trên cấu trúc hay không.
- **Thứ tự duyệt:** kết quả khi liệt kê các tác vụ có theo một quy tắc có thể dự đoán hay không.

Trong chương **Lựa chọn và thiết kế**, những bảo đảm này có thể quan trọng hơn một chênh lệch `O(1)` so với `O(log n)`. Bài học kết nối bất biến, thao tác và độ phức tạp thời gian/bộ nhớ của mảng, danh sách liên kết, bảng băm, cây, heap và đồ thị để thiết kế cấu trúc phù hợp với các yêu cầu về ổn định.

## 1. Phân biệt định danh, giá trị, vị trí, tham chiếu và bộ duyệt

Trước khi chọn cấu trúc, hãy đặt tên đúng cho thứ đang được lưu hoặc truyền giữa các thành phần.

| Khái niệm | Ví dụ | Điều nó biểu thị | Rủi ro khi hiểu nhầm |
| --- | --- | --- | --- |
| **Định danh logic (ID)** | `taskId = "T-208"` | Một thực thể cụ thể trong miền nghiệp vụ | Tái sử dụng ID không kiểm soát khiến người dùng thao tác lên thực thể mới |
| **Giá trị** | `status = "open"` | Dữ liệu hiện tại của thực thể | Hai thực thể có thể có giá trị giống nhau; giá trị có thể thay đổi |
| **Chỉ số/vị trí** | `tasks[4]` | Phần tử ở vị trí 4 **trong cấu trúc hiện tại** | Chèn/xóa/sắp xếp làm phần tử tại vị trí 4 thay đổi |
| **Tham chiếu/con trỏ** | `refToTask` | Cách truy cập đối tượng/nút hoặc vị trí lưu trữ | Đối tượng bị hủy hoặc vùng nhớ bị di chuyển có thể khiến tham chiếu không hợp lệ |
| **Iterator/cursor** | `it = tasks.begin()` | Trạng thái của một quá trình duyệt | Đổi cấu trúc trong lúc duyệt có thể làm iterator mất hiệu lực hoặc thay kết quả |
| **Khóa sắp xếp** | `(createdAt, taskId)` | Tiêu chí xếp vị trí tương đối | Thay khóa có thể đổi thứ tự dù ID vẫn giữ nguyên |

Xét mảng sau, con số trước dấu hai chấm là chỉ số:

```text
0: {id=A}   1: {id=B}   2: {id=C}   3: {id=D}

Chèn X vào đầu, giữ thứ tự cũ:
0: {id=X}   1: {id=A}   2: {id=B}   3: {id=C}   4: {id=D}

Xóa B, giữ thứ tự:
0: {id=X}   1: {id=A}   2: {id=C}   3: {id=D}
```

Trong ví dụ, **C vẫn là C**, nhưng vị trí của C đổi từ 2 sang 3 rồi lại thành 2. Bất cứ thành phần nào lưu “C ở chỉ số 2” có thể truy cập nhầm sau lần chèn đầu. Nếu thành phần lưu `id=C` và có cách tra cứu lại ID, danh tính của C có thể được giữ độc lập với vị trí.

**Bất biến quan trọng:** ID phải xác định đúng một thực thể đang hoạt động, hoặc hệ thống phải có quy tắc rõ ràng về phiên bản/tái sử dụng. Vị trí là chi tiết của cách tổ chức lưu trữ; không nên coi vị trí là định danh nghiệp vụ nếu nó có thể thay đổi.

## 2. Xác định chính xác loại ổn định ứng dụng cần

“Giữ ổn định” là yêu cầu chưa đủ cụ thể. Có thể ứng dụng chỉ cần một vài bảo đảm:

1. **ID bền vững:** sau khi di chuyển/sắp xếp dữ liệu, `get(id)` vẫn trả đúng thực thể.
2. **Chỉ số bền vững:** một chỉ số đã công bố vẫn trỏ tới cùng thực thể cho đến khi nó bị xóa, dù phần tử khác được thêm.
3. **Địa chỉ/tham chiếu bền vững:** một con trỏ hoặc tham chiếu đã lấy tiếp tục trỏ đến cùng đối tượng còn sống sau một số thao tác cho phép.
4. **Iterator bền vững:** bộ duyệt đang dùng vẫn hợp lệ sau một số thay đổi cấu trúc.
5. **Thứ tự logic bền vững:** các phần tử không bị sửa khóa vẫn giữ quan hệ trước–sau theo quy tắc.
6. **Snapshot bền vững:** một lượt đọc hoặc một chuỗi trang kết quả nhìn thấy cùng phiên bản dữ liệu, bất chấp các cập nhật diễn ra đồng thời.

Không có cấu trúc đơn lẻ nào tự động cung cấp tất cả bảo đảm ở mọi ngôn ngữ và mọi trường hợp. Ví dụ: danh sách liên kết có thể giữ địa chỉ nút khi chèn phần tử khác, nhưng không cho truy cập phần tử thứ `i` trong `O(1)`; mảng cho truy cập chỉ số nhanh nhưng di chuyển phần tử khi chèn/xóa; bảng băm cho tra cứu theo ID nhanh theo kỳ vọng nhưng thường không hứa thứ tự duyệt theo khóa.

Khi đặc tả API, hãy viết thành câu kiểm chứng được, như:

> “Khách hàng lưu `taskId`. Sau mọi thao tác thêm, xóa hoặc đổi thứ tự, `getById(taskId)` phải trả đúng tác vụ đó nếu còn tồn tại; nếu tác vụ bị xóa, yêu cầu phải báo không tồn tại, không được trả một tác vụ khác được tạo sau.”

Câu này chỉ yêu cầu **ID logic bền vững và tra cứu chính xác**, không bắt buộc ô nhớ, chỉ số hay iterator phải giữ nguyên.

## 3. Mảng và mảng động: truy cập nhanh, vị trí có thể thay đổi

Mảng hỗ trợ truy cập phần tử ở chỉ số `i` trong `O(1)`. Mảng động thường cho thêm cuối `O(1)` **khấu hao** nếu tăng dung lượng theo cấp số nhân, nhưng chèn/xóa ở giữa để giữ thứ tự thường cần dời `O(n)` phần tử.

Ba thao tác cần phân tích riêng:

| Thao tác | Phần tử logic đổi ID? | Vị trí phần tử khác có đổi? | Dữ liệu/vùng lưu có thể di chuyển? |
| --- | --- | --- | --- |
| Ghi đè giá trị không đổi ID | Không | Thường không | Tùy kiểu dữ liệu và cách lưu |
| Thêm cuối khi còn dung lượng | Không | Không | Thông thường không cần di chuyển mảng nền |
| Thêm cuối khi tăng dung lượng | Không | Chỉ số logic cũ thường giữ nguyên | **Có thể** cấp phát lại và chuyển/sao chép phần tử |
| Chèn vào giữa, giữ thứ tự | Không | **Có**, các phần tử sau điểm chèn đổi chỉ số | Có thể dịch phần tử, và có thể tăng dung lượng |
| Xóa giữa, giữ thứ tự | Phần tử bị xóa mất hiệu lực | **Có**, các phần tử sau điểm xóa đổi chỉ số | Có thể dịch phần tử |
| Sắp xếp mảng | Không | **Có**, theo khóa sắp | Phần tử được hoán đổi/di chuyển giữa các vị trí |

**Phân biệt tham chiếu tới đối tượng và tham chiếu tới ô nhớ:** trong các ngôn ngữ có đối tượng được quản lý, một mảng/list có thể chứa *tham chiếu đến đối tượng*. Khi mảng nền của list được thay, tham chiếu đã lấy đến chính đối tượng đó có thể vẫn hợp lệ nếu đối tượng còn sống. Trong ngôn ngữ lưu phần tử trực tiếp trong vùng nhớ của mảng, cấp phát lại có thể làm con trỏ/tham chiếu vào phần tử cũ mất hiệu lực. Quy tắc cụ thể phải xem theo kiểu container và ngôn ngữ đang dùng.

Chẳng hạn, đối với `std::vector<T>` trong C++, thao tác làm tăng `capacity` có thể làm mất hiệu lực mọi iterator, con trỏ và tham chiếu vào các phần tử cũ; thao tác chèn/xóa cũng có các quy tắc invalidation theo vị trí. Đối với `ArrayList<Task>` trong Java, việc thay mảng chứa các tham chiếu không tự làm một biến Java kiểu `Task` trỏ sang đối tượng khác, nhưng **iterator của danh sách** có thể bị ảnh hưởng bởi thay đổi cấu trúc và thường theo chính sách fail-fast ở mức nỗ lực tốt nhất.

Vì vậy, API nên thể hiện đúng thứ mà người dùng được giữ lâu dài: **ID hay handle**, **đối tượng còn sống**, **chỉ số tạm**, hay **iterator chỉ hợp lệ trong phiên duyệt**.

### 3.1. Xóa nhanh bằng đổi chỗ với cuối mảng

Nếu **không cần giữ thứ tự**, có thể xóa phần tử ở vị trí `i` bằng cách đưa phần tử cuối vào đó rồi giảm kích thước:

```text
eraseUnordered(i):
    A[i] = A[n - 1]
    n -= 1
```

Trong mô hình mảng và phép chuyển phần tử có chi phí hằng số, thao tác này mất `O(1)` sau khi đã biết vị trí. Nhưng nếu `A[i]` từng là B và `A[n-1]` là D, D sẽ chuyển tới `i`. **Thứ tự duyệt bị thay đổi**, và mọi nơi lưu chỉ số cũ của D phải được cập nhật.

Nếu còn bản đồ `idToIndex`, cách xóa phải sửa bản đồ đó cùng lúc; phần tử bị xóa phải được bỏ khỏi chỉ mục. Chỉ cần quên sửa ánh xạ của phần tử cuối là sinh lỗi “ID đúng nhưng trỏ sai phần tử”.

### 3.2. Chỉ số có thể ổn định khi không dồn phần tử

Một kỹ thuật khác là giữ **ô trống** sau khi xóa thay vì dịch phần tử:

```text
slot[0] = A
slot[1] = EMPTY     // B đã xóa
slot[2] = C
slot[3] = D
```

Khi đó, vị trí của C và D không đổi. Đổi lại:

- Có thể mất thời gian quét các ô trống khi duyệt.
- Cần cơ chế quản lý ô trống (free list, bitmap, v.v.).
- Khi tái sử dụng `slot[1]` cho X, người dùng từng giữ “ô 1 là B” có thể truy cập nhầm X.
- Nếu nén/di chuyển lại các ô để tiết kiệm bộ nhớ, chỉ số có thể mất tính ổn định.

Giữ vị trí không tự giải quyết **định danh của một vòng đời đối tượng**. Đó là lý do cần handle có phiên bản khi dùng lại ô.

## 4. Danh sách liên kết: ổn định nút, nhưng có chi phí tìm kiếm

Danh sách liên kết đôi gồm các nút có con trỏ `prev`/`next`. Khi đã có tham chiếu hợp lệ đến nút:

- Chèn nút trước/sau: cập nhật số liên kết hằng số, `O(1)`.
- Xóa chính nút đó: cập nhật liên kết `O(1)`, sau đó nút bị xóa không còn hợp lệ.
- Chèn hoặc xóa nút khác thường không cần di chuyển các nút còn lại.

Đặc tính này hữu ích khi cần **giữ các tham chiếu đến nút sống** trong lúc thêm/xóa ở vị trí khác. Tuy nhiên:

- Tìm một nút từ khóa có thể mất `O(n)` nếu chỉ có danh sách.
- Truy cập phần tử thứ `i` cần đi qua các liên kết, thường `O(n)`.
- Nút đã xóa có thể bị giải phóng; con trỏ cũ trở thành dangling pointer trong môi trường quản lý bộ nhớ thủ công.
- Nút có thể được cấp phát lại ở cùng địa chỉ cho thực thể khác; địa chỉ vật lý tự nó không phải danh tính bền vững.

Có thể phối hợp **hash map `id → node`** với danh sách liên kết đôi để vừa tra cứu ID kỳ vọng `O(1)` vừa chèn/xóa nút đã biết trong `O(1)`, đồng thời duyệt theo thứ tự liên kết. Đây là cơ chế thường gặp khi phải giữ **thứ tự truy cập gần nhất**, chẳng hạn cấu trúc nền cho cache LRU.

Bất biến của cấu trúc ghép: mỗi `id` trong map trỏ đến đúng một nút còn sống trong danh sách; mỗi nút trong danh sách xuất hiện đúng một lần trong map; `prev` và `next` luôn đối xứng. Một lỗi cập nhật ở một trong hai nơi có thể phá tra cứu hoặc thứ tự duyệt.

## 5. Bảng băm, cây có thứ tự và heap: ba cách nhìn khác nhau

### 5.1. Hash map: ID ổn định nhờ khóa, vị trí lưu không nhất thiết ổn định

Với `byId: HashMap<Id, Task>`, khách hàng lưu `id` và gọi `byId.get(id)` khi cần. Bảng băm có thể thay dung lượng và di chuyển mục nội bộ mà không thay đổi **quan hệ ánh xạ logic** từ ID đến tác vụ.

Đây là bảo đảm mạnh hơn việc nhớ vị trí bucket: người dùng không cần biết mục nằm ở đâu. Nhưng cần nêu rõ:

- ID phải duy nhất theo chính sách nghiệp vụ.
- Trường được dùng làm khóa băm phải không đổi trong thời gian khóa còn trong map hoặc phải xóa/chèn lại đúng cách khi đổi.
- Hash map thông thường **không bảo đảm thứ tự duyệt theo khóa**; một lần rehash có thể thay thứ tự duyệt.
- Con trỏ/iterator/tham chiếu tới phần tử bên trong bảng băm có các quy tắc hợp lệ riêng tùy thư viện; không tự động suy từ việc `get(id)` vẫn đúng.
- Tra cứu có chi phí kỳ vọng `O(1)` trong điều kiện băm phù hợp, trường hợp xấu có thể cao hơn.

**Ổn định định danh không đồng nghĩa ổn định địa chỉ.** Một API chỉ cho phép lấy lại phần tử bằng `id` tránh phụ thuộc vào nơi bảng lưu phần tử.

### 5.2. Cây tìm kiếm tự cân bằng: thứ tự theo khóa, ID và vị trí cây

Một cây tìm kiếm tự cân bằng theo khóa `(createdAt, taskId)` cho phép:

- Tìm/chèn/xóa theo khóa trong `O(log n)` trường hợp xấu ở mô hình chuẩn.
- Duyệt theo thứ tự tăng dần của khóa.
- Tìm cận dưới và liệt kê `k` phần tử trong `O(log n+k)`.

Khi cây xoay để cân bằng, **vị trí hình học của nút trong cây thay đổi**. Khóa và danh tính logic của phần tử không cần đổi. Tuy vậy, tham chiếu/iterator có còn hợp lệ qua phép xoay hay không phụ thuộc cấu trúc cụ thể và hợp đồng thư viện; với cây lưu nút ổn định, thường có thể giữ tham chiếu tới nút còn sống, còn với cấu trúc dựa trên mảng hoặc tái xây khác thì không thể mặc định.

Cần phân biệt **thứ tự khóa** với **thứ tự chèn**: cây theo `createdAt` không hứa đưa phần tử mới chèn ra cuối nếu nó mang timestamp cũ. Nếu khóa sắp có thể trùng, khóa ghép thêm ID hoặc cấu trúc multimap có quy tắc riêng giúp bảo toàn mọi phần tử.

### 5.3. Heap: giữ ưu tiên nhưng không giữ vị trí của phần tử

Heap nhị phân lưu các phần tử trong mảng sao cho nút cha có mức ưu tiên không kém con. Chỉ **đỉnh heap** được bảo đảm là phần tử có ưu tiên cao nhất hoặc thấp nhất (tùy min/max heap). Các phần tử khác không được sắp đầy đủ.

Khi `push`, `popMin` hoặc thay đổi ưu tiên, thuật toán `siftUp`/`siftDown` hoán đổi nhiều phần tử. Vì vậy, một phần tử có thể chuyển sang chỉ số khác sau mỗi thao tác, dù ID không đổi.

Nếu chỉ cần `peekMin` và `popMin`, heap phù hợp. Nếu phải hủy hoặc cập nhật mức ưu tiên của tác vụ theo ID, có thể dùng:

```text
heap:      array<Task>
posById:   HashMap<Id, Index>

swap(i, j):
    swap(heap[i], heap[j])
    posById[heap[i].id] = i
    posById[heap[j].id] = j
```

Mọi lần hoán đổi phải cập nhật cả hai ánh xạ. Bất biến là `posById[heap[i].id] = i` với mọi phần tử đang ở heap; một lần quên cập nhật làm thao tác theo ID tác động nhầm vị trí.

Với tìm ID kỳ vọng `O(1)` qua map và điều chỉnh heap `O(log n)`, có thể sửa mức ưu tiên trong `O(log n)` kỳ vọng tổng thể khi giả định triển khai phù hợp. Nếu mảng nền cần mở rộng, chi phí một lần thêm còn có thể có phần cấp phát/sao chép tuyến tính; cần phân biệt bảo đảm khấu hao và trường hợp xấu.

## 6. Định danh bền vững: dùng ID để tách logic khỏi nơi lưu

Một kiến trúc đơn giản là giữ bản ghi và chỉ mục:

```text
Task:
    id: TaskId
    createdAt: Timestamp
    state: TaskState

byId: Map<TaskId, Task>
orderByCreatedAt: OrderedIndex<(Timestamp, TaskId)>
```

Các thành phần bên ngoài chỉ giữ `TaskId`. Khi cần dữ liệu, gọi `byId.get(id)`. Khi cần báo cáo, dùng `orderByCreatedAt` để lấy các ID theo thứ tự rồi tra lại bản ghi.

Để đáp ứng yêu cầu, cần định nghĩa:

- **Phạm vi duy nhất:** `TaskId` không trùng trong toàn hệ thống hay chỉ trong một dự án?
- **Vòng đời:** sau khi xóa, cùng ID có bao giờ được cấp lại cho thực thể khác không?
- **Tham chiếu stale:** nếu một thành phần gọi `get(id)` sau khi thực thể bị xóa, trả `NOT_FOUND` hay thông báo “đã hết hạn”?
- **Đổi khóa:** ID có bất biến không? Nếu phải đổi ID, thao tác ấy có phải tạo định danh mới hoặc duy trì alias?
- **Phạm vi đồng thời:** tra cứu và xóa cùng lúc được tuần tự hóa, trả snapshot hay có quy tắc nhất quán khác?

**Cách an toàn về ngữ nghĩa:** coi ID là bất biến trong vòng đời và tránh tái sử dụng nếu không có cơ chế phân biệt các thế hệ. ID có thể là số tăng dần, UUID hoặc khóa do hệ thống cấp; lựa chọn cụ thể còn tùy yêu cầu quy mô, tính duy nhất và cách phân tán.

### 6.1. Khi ID là chỉ số nội bộ: cần handle có thế hệ

Đôi khi cấu trúc muốn lưu dữ liệu gọn trong một mảng ô và tái sử dụng ô trống. Nếu API trả thẳng vị trí, một lỗi **ABA** có thể xảy ra:

```text
handle cũ = 5
slot[5] chứa A

xóa A -> slot[5] trống
thêm B -> tái sử dụng slot[5]

handle cũ = 5 bây giờ lại truy cập B!
```

Để phát hiện handle cũ, dùng cặp **`Handle(index, generation)`**, gọi là *generational handle*:

```text
Handle {
    index
    generation
}

Slot {
    generation
    occupied
    value
}

get(h):
    if h.index ngoài miền slots:
        return NOT_FOUND
    s = slots[h.index]
    if not s.occupied or s.generation != h.generation:
        return STALE_HANDLE
    return s.value
```

Khi xóa một ô, đánh dấu không còn sử dụng và tăng thế hệ trước khi có thể tái sử dụng. Khi thêm phần tử vào ô trống, cấp handle mới với thế hệ hiện tại của ô. Mã giả khép kín:

```text
create(value):
    if freeList không rỗng:
        i = freeList.pop()
        s = slots[i]
    else:
        i = slots.length
        s = Slot(generation=0, occupied=false, value=EMPTY)
        slots.append(s)

    assert not s.occupied
    s.value = value
    s.occupied = true
    return Handle(i, s.generation)

remove(h):
    if not valid(h):
        return STALE_HANDLE
    s = slots[h.index]
    s.value = EMPTY
    s.occupied = false
    s.generation += 1
    freeList.push(h.index)
    return OK

valid(h):
    return 0 <= h.index < slots.length
       and slots[h.index].occupied
       and slots[h.index].generation == h.generation
```

Trong mô hình này, handle vẫn tìm đúng **ô logic** sau khi mảng chứa các `Slot` được cấp phát lại, vì truy cập được thực hiện qua chỉ số; tuy nhiên con trỏ trực tiếp đến `Slot` vẫn có thể mất hiệu lực khi vùng mảng di chuyển. Việc cấp phát lại cũng không ảnh hưởng cặp số `(index,generation)` đã cấp.

**Giới hạn và giả định:**

- Nếu bộ đếm thế hệ là số nguyên hữu hạn và tăng đủ nhiều để **quay vòng**, một handle rất cũ có thể trùng lại. Phải chọn kích thước bộ đếm, chính sách chống wrap hoặc quy tắc tái sử dụng phù hợp yêu cầu.
- Nếu nén mảng bằng cách **đổi vị trí ô**, các handle theo chỉ số sẽ bị sai, trừ khi có lớp ánh xạ ổn định khác.
- Phân tích `O(1)` cho `get`/`create`/`remove` là theo truy cập mảng và thao tác free list; khi mảng tăng dung lượng, một lần `create` có thể mất `O(n)`, thông thường thêm cuối có chi phí `O(1)` khấu hao.
- Nếu nhiều luồng truy cập đồng thời, kiểm tra thế hệ **không thay thế khóa, nguyên tử hay cơ chế quản lý vòng đời**. Một luồng có thể xóa ô ngay sau khi luồng khác kiểm tra `valid(h)`; cần bảo đảm phạm vi sống của kết quả đọc.

Generational handle cho **phát hiện tái sử dụng ô**, không tự hứa thứ tự duyệt ổn định. Để duyệt theo thời gian, cần thêm một cấu trúc thứ tự hoặc metadata thích hợp.

### 6.2. Bảng so sánh hai phương pháp lưu ID

| Thiết kế | Tra cứu theo danh tính | Dữ liệu có thể di chuyển? | Chi phí và giới hạn |
| --- | --- | --- | --- |
| `HashMap<BusinessId, Record>` | Kỳ vọng `O(1)` | Có thể, tùy triển khai | ID không phụ thuộc vị trí, cần quản lý khóa và bộ nhớ bảng |
| `SlotMap<Handle(index,generation), Record>` | `O(1)` theo chỉ số hợp lệ | Mảng `Slot` có thể dời nguyên khối | Handle hết hiệu lực khi xóa; quản lý free list và thế hệ |
| `BalancedBST<Id, Record>` | `O(log n)` trường hợp xấu | Nút/vị trí cây tùy triển khai | Có thứ tự khóa, thêm metadata và chi phí cân bằng |
| `Array<Record> + Map<Id,Index>` | Kỳ vọng `O(1)` qua map | Có thể khi chèn/xóa/sắp xếp | Phải đồng bộ mọi chỉ số sau thao tác đổi vị trí |

*Slot map* là một họ cấu trúc dựa trên ô và handle; không phải mọi thư viện slot-map hiện thực giống hoàn toàn mã giả ở trên. Cần kiểm tra tính chất bộ nhớ, hiệu năng, quy tắc tái sử dụng và thread safety của triển khai thực tế.

## 7. Thứ tự duyệt: thứ tự nào mới là hợp đồng?

Một API `listTasks()` không nói rõ thứ tự thì ứng dụng khách có thể vô tình dựa vào thứ tự “tình cờ” của cấu trúc nội bộ. Hãy chỉ định **quan hệ thứ tự** ngay trong hợp đồng.

| Loại thứ tự | Ví dụ | Cấu trúc có thể hỗ trợ |
| --- | --- | --- |
| **Theo chỉ số hiện tại** | Phần tử ở `A[0], A[1], ...` | Mảng, mảng động |
| **Theo thứ tự chèn** | Tác vụ nào được thêm trước thì liệt kê trước | Mảng nếu không hoán đổi; danh sách liên kết; cấu trúc duy trì thứ tự chèn |
| **Theo thứ tự truy cập** | Phần tử lâu chưa dùng đứng đầu (LRU) | Danh sách liên kết + map |
| **Theo khóa tăng/giảm** | Theo `(createdAt, taskId)` | Mảng sắp, cây tìm kiếm tự cân bằng |
| **Theo ưu tiên cực trị** | Liên tục lấy tác vụ có mức ưu tiên cao nhất | Heap cho thao tác lấy đỉnh; không hỗ trợ duyệt toàn bộ đã sắp trực tiếp |
| **Theo lịch sử phiên bản** | Liệt kê như tại thời điểm bắt đầu báo cáo | Snapshot bất biến hoặc cơ chế versioning |

Một **hash map thông thường** không đảm bảo thứ tự tăng dần của khóa. Một hash map có duy trì thứ tự chèn trong một ngôn ngữ nào đó cũng **không tự cho thứ tự theo thời gian tạo** nếu thời gian tạo không trùng với thứ tự chèn.

Tương tự, **stable sort** và **stable identity** là hai khái niệm khác nhau. Thuật toán sắp xếp ổn định chỉ bảo đảm các phần tử có khóa sắp bằng nhau giữ nguyên **thứ tự tương đối trước khi sắp**; nó không bảo đảm vị trí, con trỏ hay iterator sẽ không thay đổi sau khi sắp.

### 7.1. Khóa ghép cho thứ tự tất định

Nếu hai tác vụ có cùng `createdAt`, chỉ sắp theo `createdAt` chưa đủ để xác định thứ tự của cặp đó. Nên định nghĩa khóa ghép:

```text
orderKey(task) = (task.createdAt, task.taskId)
```

Nếu `taskId` duy nhất và quan hệ so sánh trên hai thành phần nhất quán, khóa ghép tạo **thứ tự toàn phần rõ ràng**. Khi liệt kê, hệ thống không cần dựa vào thứ tự chèn ngẫu nhiên để phá hòa.

Nếu tác vụ có thể sửa `createdAt`, phải cập nhật chỉ mục thứ tự: xóa khóa cũ rồi chèn khóa mới. ID logic vẫn giữ nguyên nhưng **vị trí trong kết quả có chủ đích thay đổi**. Đây không phải vi phạm ổn định danh tính; đây là thay đổi theo đúng quy tắc sắp xếp.

### 7.2. Ổn định thứ tự của các phần tử còn sống

Định nghĩa hai kiểu bảo đảm khác nhau:

- **Giữ thứ tự tương đối:** nếu B đứng trước C và không có thao tác đổi thứ tự hai phần tử ấy, sau khi chèn/xóa phần tử khác B vẫn trước C.
- **Giữ vị trí tuyệt đối:** B luôn đứng ở chỉ số cố định, ngay cả khi phần tử trước nó bị chèn/xóa.

Danh sách liên kết hoặc mảng được chèn/xóa theo cách giữ thứ tự có thể đáp ứng **thứ tự tương đối**, nhưng chỉ số tuyệt đối của phần tử trong mảng vẫn có thể thay đổi. Nếu muốn giữ vị trí tuyệt đối, phải định nghĩa xử lý ô trống, mã hóa vị trí ổn định hoặc một ánh xạ trung gian; sự đánh đổi thường là bộ nhớ và công sức quản lý.

### 7.3. Duyệt lúc cấu trúc đang thay đổi

Một bộ duyệt được tạo ở thời điểm `t0` có thể gặp các trường hợp:

- Cấu trúc thêm phần tử vào trước vị trí đang duyệt.
- Cấu trúc xóa chính phần tử mà iterator đang trỏ tới.
- Hash map rehash trong khi iterator đang duyệt các bucket.
- Cây sắp lại vị trí các nút do cập nhật; hoặc cập nhật khóa sắp khiến phần tử đổi chỗ.
- Luồng khác sửa dữ liệu ngay trong lúc đang đọc.

Không thể suy hành vi chung từ tên cấu trúc. Các **chính sách duyệt** phổ biến:

1. **Cấm sửa cấu trúc trong phiên duyệt:** chỉ cho phép cập nhật sau khi iterator kết thúc; dễ kiểm soát bất biến.
2. **Iterator bị vô hiệu hóa theo quy tắc thư viện:** khi xảy ra thay đổi bị cấm, việc sử dụng tiếp không hợp lệ hoặc phát hiện lỗi.
3. **Fail-fast:** bộ duyệt cố phát hiện thay đổi ngoài mong đợi và ném lỗi; nhiều triển khai chỉ bảo đảm *best effort*, không dùng làm cơ chế an toàn luồng.
4. **Weakly consistent:** bộ duyệt được phép nhìn một phần thay đổi đồng thời, không nhất thiết là một snapshot tại thời điểm duy nhất; ngữ nghĩa do thư viện định nghĩa.
5. **Snapshot iterator:** duyệt phiên bản bất biến hoặc bản sao tại `t0`, không bị ảnh hưởng bởi các cập nhật sau đó trong phạm vi snapshot.

Để tạo báo cáo tài chính cần số liệu nhất quán tại một thời điểm, chỉ có **thứ tự tất định** là chưa đủ: còn cần **tính nhất quán của phiên bản đọc**. Một tập kết quả được sắp đúng nhưng lẫn phần tử trước và sau cập nhật vẫn có thể sai về nghiệp vụ.

## 8. Phân trang: tại sao offset có thể lặp hoặc bỏ sót phần tử?

Giả sử danh sách sắp theo `(createdAt, taskId)`:

```text
[ A, B, C, D, E, F ]
Trang 1, LIMIT 3 OFFSET 0 → [A, B, C]
```

Sau khi người dùng đọc trang 1, có tác vụ X được chèn trước A:

```text
[ X, A, B, C, D, E, F ]
Trang 2, LIMIT 3 OFFSET 3 → [C, D, E]
```

C xuất hiện ở **cả trang 1 lẫn trang 2**. Nếu xóa phần tử phía trước offset, có thể xảy ra tình huống bỏ sót. Vấn đề đến từ việc offset đo **vị trí hiện tại**, không phải định danh hoặc mốc thứ tự cố định.

### 8.1. Phân trang theo khóa cuối (*keyset pagination*)

Nếu thứ tự sắp là khóa ghép duy nhất `(createdAt, taskId)`, có thể dùng khóa cuối trang trước làm cursor:

```text
page1 = first 3 tasks ordered by (createdAt, taskId)
cursor = orderKey(page1.last)

page2 = first 3 tasks satisfying orderKey(task) > cursor
        ordered by (createdAt, taskId)
```

Ưu điểm: những bản ghi được chèn/xóa **trước cursor** không tự làm đổi điểm bắt đầu của trang kế tiếp, nên tránh một số trường hợp lặp/bỏ sót do offset dịch. Cần dùng thứ tự toàn phần và so sánh nhất quán, bao gồm quy tắc xử lý khóa trùng, chiều tăng/giảm và bộ lọc.

Nhưng **keyset không tự tạo snapshot**. Bản ghi mới được thêm **sau cursor** có thể xuất hiện ở trang tiếp theo, và thay đổi khóa sắp có thể làm một bản ghi đi qua cursor. Nếu yêu cầu mọi trang cùng thuộc một bản chụp `t0`, cần snapshot/phiên bản đọc ổn định ngoài keyset.

### 8.2. Không dùng index mảng như ID trả về API

Một API như `GET /tasks/17` thường nên hiểu 17 là **định danh** nếu hợp đồng nói vậy. Nếu thực tế 17 chỉ là vị trí trong mảng, sau khi sort hay xóa phần tử, cùng URL có thể trả một tác vụ khác. Đây là lỗi ngữ nghĩa, không chỉ lỗi hiệu năng.

Hãy tách rõ:

```text
getById(id)          // danh tính logic
getAt(index)         // vị trí trong dãy hiện tại
listAfter(orderKey)  // điểm tiếp theo trong thứ tự duyệt
```

Ba giao diện này có quy tắc ổn định và xử lý lỗi khác nhau.

## 9. Ví dụ hoàn chỉnh: danh sách công việc có ID bền vững và thứ tự tạo

Một hệ thống quản lý tác vụ cần:

- `create(task)`, `getById(id)`, `cancel(id)`.
- Truy vấn `earliest(k)` trả `k` tác vụ tạo sớm nhất theo `(createdAt, id)`.
- ID không thay đổi và không được tái sử dụng cho tác vụ khác.
- Xóa một tác vụ không làm những ID còn sống trỏ sang tác vụ khác.
- Báo cáo duyệt theo thứ tự tất định; nếu cần snapshot nhất quán, phải có cơ chế phiên bản riêng.

Ta chọn:

```text
byId: Map<TaskId, TaskRecord>
byCreatedAt: BalancedBST<(CreatedAt, TaskId)>

Invariant:
    mọi task còn sống trong byId có đúng một khóa
    (task.createdAt, task.id) trong byCreatedAt

    và mọi khóa trong byCreatedAt trỏ về đúng task trong byId
```

Sơ đồ liên hệ:

```text
                    byId
 ID A ────────────> Task A {createdAt: 09:00}
 ID B ────────────> Task B {createdAt: 08:30}
 ID C ────────────> Task C {createdAt: 09:00}

                  byCreatedAt
            (08:30, B) → B
            (09:00, A) → A
            (09:00, C) → C
```

Khách hàng lưu `TaskId` chứ không lưu vị trí của nút cây hay bucket. Nếu chỉ mục cây tái cân bằng, ID và kết quả `getById` vẫn đúng.

### 9.1. Các thao tác và bất biến

```text
create(task):
    assert task.id chưa tồn tại trong byId
    // toàn bộ thay đổi cần được thực hiện như một đơn vị logic
    byId.insert(task.id, task)
    byCreatedAt.insert((task.createdAt, task.id))
    // nếu có lỗi, rollback để tránh chỉ mục lệch nhau

cancel(id):
    task = byId.get(id)
    if task == NOT_FOUND:
        return NOT_FOUND
    byCreatedAt.delete((task.createdAt, id))
    byId.delete(id)
    // nếu lỗi giữa chừng, rollback để giữ bất biến

earliest(k):
    keys = lấy tối đa k khóa đầu từ byCreatedAt
    return [byId.get(id) cho mỗi (_, id) trong keys]
```

Các cập nhật thực sự phải giữ tính **nguyên tử quan sát được** khi có đọc/ghi đồng thời; trình tự mã giả chỉ minh họa những bước cần thực hiện. Có thể dùng giao dịch, khóa đồng bộ hoặc cơ chế snapshot tùy hệ thống. Nếu ID được cấp trước khi transaction hoàn tất, cần xác định lại trạng thái của ID khi rollback.

### 9.2. Độ phức tạp dự kiến

Với `n` tác vụ đang hoạt động, `k` kết quả trả về:

| Phép toán | Chi phí |
| --- | --- |
| `getById(id)` | Kỳ vọng `O(1)` với hash map thông dụng |
| `create(task)` | Kỳ vọng `O(1)` cho map và `O(log n)` cho cây; tổng `O(log n)` kỳ vọng |
| `cancel(id)` | Tìm bằng map kỳ vọng `O(1)`, xóa ở cây `O(log n)`, xóa map kỳ vọng `O(1)` |
| `earliest(k)` | `O(log n+k)` theo chỉ mục cây và `k` lần tra map kỳ vọng `O(1)` |
| Bộ nhớ chỉ mục | `O(n)` cho map và `O(n)` cho cây, bên cạnh dữ liệu bản ghi |

Tất cả thao tác có bảo đảm **ngữ nghĩa danh tính** khi các bất biến được giữ. Không có cam kết rằng địa chỉ bucket, vị trí nút trong cây hoặc iterator sau cập nhật luôn giống trước. Đó là một quyết định thiết kế có chủ ý.

Nếu ứng dụng yêu cầu **thứ tự chèn** thay vì thời gian tạo, cây theo `createdAt` là lựa chọn không đúng ngữ nghĩa. Có thể dùng danh sách liên kết theo thứ tự chèn và map `id → node`. Đổi lại, truy vấn “tác vụ có `createdAt` nhỏ nhất” sẽ cần một chỉ mục khác hoặc quét.

## 10. Bài toán đồ thị: đỉnh và cạnh có danh tính riêng

Trong đồ thị, mỗi đỉnh có thể mang `vertexId` (mã người dùng, thiết bị hoặc dịch vụ). Thuật toán thường đánh số đỉnh thành `0..V-1` để lưu danh sách kề hoặc ma trận kề hiệu quả.

Cần phân biệt:

- **VertexId:** định danh nghiệp vụ của đỉnh, có thể tồn tại lâu dài.
- **VertexIndex:** chỉ số dense được thuật toán gán trong một phiên bản đồ thị.
- **EdgeId:** nếu cạnh có danh tính riêng (ví dụ hợp đồng/kết nối có nhiều thuộc tính), cần chính sách ID riêng.
- **Thứ tự duyệt BFS/DFS:** phụ thuộc đỉnh bắt đầu, thứ tự xét hàng xóm và quy tắc xếp hàng/ngăn xếp, không có một thứ tự duy nhất cho mọi biểu diễn.

Ví dụ, `vertexId=U102` được ánh xạ thành chỉ số 7. Nếu xóa một đỉnh khác và dồn mảng đỉnh, `U102` có thể chuyển chỉ số; toàn bộ danh sách kề hoặc ma trận tham chiếu chỉ số cũ phải cập nhật nếu muốn giữ biểu diễn chính xác.

Ba phương án phổ biến:

1. **Giữ ID làm khóa trong adjacency map:** `Map<VertexId, Set<VertexId>>`; dễ giữ danh tính logic, nhưng tốn overhead và phụ thuộc chi phí map/set.
2. **Duy trì `vertexId → denseIndex`:** hiệu quả cho thuật toán dùng mảng/CSR, nhưng nếu thay thứ tự hoặc tái đánh số phải cập nhật mọi ánh xạ và cạnh liên quan.
3. **Snapshot đồ thị có ánh xạ phiên bản:** khi chạy thuật toán, cố định ánh xạ ID ↔ chỉ số cho phiên bản đó; bản cập nhật tiếp theo có thể tạo ánh xạ mới, không dùng chỉ số từ phiên bản cũ nếu không được xác nhận.

Nếu muốn kết quả duyệt đồ thị **tất định**, có thể sắp hàng xóm theo `vertexId` hoặc định nghĩa một thứ tự ưu tiên rõ ràng trước khi BFS/DFS. Cần tính chi phí sắp xếp hoặc duy trì hàng xóm có thứ tự; chỉ thay đổi cấu trúc lưu trữ cạnh có thể làm thứ tự gặp đỉnh khác đi mà không làm thay đổi tập đỉnh có thể đi tới.

## 11. Đồng thời, vòng đời đối tượng và ABA

Một tham chiếu “còn đúng” trong môi trường đơn luồng chưa chắc an toàn khi có nhiều luồng.

Giả sử luồng A đọc một handle và kiểm tra thế hệ, còn luồng B xóa phần tử rồi tái sử dụng ô. Nếu A đọc giá trị sau khi B sửa mà không đồng bộ, A có thể gặp tranh chấp hoặc đọc trạng thái không nhất quán. **Kiểm tra thế hệ không tự tạo bảo đảm an toàn bộ nhớ hay tính nguyên tử**.

Các giải pháp khả thi tùy mục tiêu:

- **Khóa cho phiên đọc/ghi:** trong thời gian dùng đối tượng, luồng khác không được xóa hoặc di chuyển theo cách gây mất hiệu lực.
- **Đối tượng có quyền sở hữu/vòng đời rõ ràng:** dùng smart pointer, reference counting hoặc cơ chế thu hồi an toàn khi phù hợp ngôn ngữ, nhưng vẫn cần đồng bộ nếu sửa dữ liệu dùng chung.
- **Snapshot bất biến:** truy vấn trên phiên bản dữ liệu không đổi; cập nhật tạo/đưa vào phiên bản mới theo quy tắc.
- **Cơ chế thu hồi đồng thời chuyên dụng:** hazard pointers, epoch-based reclamation/RCU trong các hệ thống cần hiệu năng cao, đi kèm chứng minh đúng đắn và giới hạn bộ nhớ.

**ABA** cũng xuất hiện trong thuật toán đồng thời khi một vị trí/trạng thái chuyển từ A sang B rồi trở lại A, khiến một phép so sánh tưởng rằng không có thay đổi. Bộ đếm thế hệ có thể góp phần phát hiện một số dạng ABA khi thiết kế đúng, nhưng không thay thế phân tích đồng thời, vòng đời bộ nhớ và rào cản bộ nhớ.

Đối với một bài học nhập môn, có thể áp dụng quy tắc an toàn: **không chia sẻ iterator hoặc tham chiếu có thể bị mất hiệu lực qua các luồng nếu chưa có hợp đồng đồng bộ rõ ràng**.

## 12. Cách chọn cấu trúc theo bảo đảm cần giữ

Trước khi cài đặt, hãy điền bảng “hợp đồng ổn định” sau:

| Câu hỏi | Câu trả lời cần ghi rõ |
| --- | --- |
| Ai giữ tham chiếu và trong bao lâu? | Một hàm cục bộ, một phiên giao dịch, phiên duyệt hay API khách hàng qua nhiều ngày? |
| Cái gì phải ổn định? | ID, chỉ số, địa chỉ, iterator, thứ tự tương đối, hay toàn bộ snapshot? |
| Phép toán nào được phép khi tham chiếu còn sống? | Thêm cuối, chèn giữa, xóa, sắp xếp, resize, rehash, cập nhật khóa, thao tác đồng thời? |
| Khi phần tử bị xóa thì sao? | Trả lỗi, vô hiệu handle, giữ tombstone, hay dùng phiên bản? |
| Có cho tái sử dụng vị trí hoặc ID không? | Cần thế hệ, ID duy nhất lâu dài hoặc luật hết hạn rõ ràng |
| Thứ tự duyệt là gì? | Thứ tự chèn, thứ tự khóa ghép, theo truy cập, theo ưu tiên hay theo snapshot? |
| Chi phí được chấp nhận? | `get`/`update`/`iterate`, bộ nhớ, thời gian duy trì chỉ mục, đồng thời |
| Tính nhất quán đọc? | Đọc trực tiếp, khóa cho toàn bộ lượt duyệt, snapshot hoặc weak consistency? |

Một số lựa chọn điển hình:

| Nhu cầu chính | Phương án đáng xét | Đánh đổi phải chấp nhận |
| --- | --- | --- |
| Truy cập theo vị trí, ít chèn giữa | Mảng/mảng động | `O(1)` theo chỉ số; cần quy tắc khi đổi vị trí/cấp phát |
| ID bền vững, tìm chính xác rất nhiều | Hash map theo ID | Kỳ vọng `O(1)`; iterator/thứ tự nội bộ tùy triển khai |
| ID bền vững + duyệt theo thứ tự chèn | Hash map + danh sách liên kết | Giữ hai cấu trúc nhất quán, thêm liên kết/bộ nhớ |
| ID bền vững + duyệt theo khóa | Hash map + cây theo khóa, hoặc chỉ cây theo ID nếu phù hợp truy vấn | Cập nhật chỉ mục có thứ tự, `O(log n)` |
| Muốn giữ tham chiếu đến nút sống khi chèn/xóa nút khác | Danh sách nút hoặc cấu trúc node-based có hợp đồng phù hợp | Truy cập ngẫu nhiên kém, chi phí cấp phát nút |
| Dữ liệu compact trong mảng, xóa/tái sử dụng ô | Slot map với handle thế hệ | Quản lý free list và thế hệ, không tự ổn định thứ tự duyệt |
| Heap cần đổi ưu tiên/xóa theo ID | Heap + bản đồ ID → vị trí | Mọi lần swap phải cập nhật chỉ mục |
| Duyệt báo cáo qua nhiều trang khi dữ liệu thay đổi | Khóa sắp tất định + keyset; snapshot nếu cần nhất quán phiên bản | Cần chỉ mục thứ tự và chính sách phiên bản |
| Duyệt đồ thị với ID đỉnh bền vững | Map ID → chỉ số theo phiên bản hoặc adjacency map theo ID | Phải tránh dùng chỉ số cũ sau tái đánh số |

### Quy trình kiểm tra bất biến

Có thể kiểm thử bằng các chuỗi thao tác **có khả năng làm thay đổi vị trí**:

1. Tạo A, B, C; lấy ID/handle của B; chèn X vào đầu hoặc khiến mảng phải tăng dung lượng; xác nhận `get(B)` vẫn trả B.
2. Xóa B; tạo D vào ô được tái sử dụng; xác nhận handle cũ của B bị từ chối và không truy cập D.
3. Đổi khóa sắp của C; xác nhận chỉ mục thứ tự di chuyển C đúng vị trí nhưng ID của C không đổi.
4. Với heap, sửa mức ưu tiên khiến các phần tử hoán đổi; kiểm tra mọi `posById[id]` trỏ tới đúng phần tử.
5. Duyệt khi có cập nhật; xác nhận hành vi đúng với hợp đồng: cấm sửa, fail-fast, weakly consistent hoặc snapshot.
6. Tạo nhiều phần tử có cùng khóa sắp chính; xác nhận khóa ghép hoặc quy tắc phá hòa tạo thứ tự tất định.
7. Phân trang rồi chèn/xóa trước vị trí bắt đầu trang kế tiếp; kiểm tra keyset và điều kiện snapshot theo yêu cầu.

Nếu dùng thiết kế nhiều chỉ mục, sau mọi thao tác cập nhật hãy kiểm tra bất biến **hai chiều**: mỗi phần tử tồn tại có mặt đúng một lần trong mọi chỉ mục cần thiết, và không có chỉ mục nào trỏ đến phần tử đã xóa. Khi thử đồng thời, cần bổ sung kiểm thử về tuần tự hóa cập nhật và vòng đời tham chiếu.

## 13. Tự kiểm tra

**Bài 1 — Chỉ số và ID.** Một ứng dụng giữ `selectedIndex = 4` để nhớ tác vụ đang được chọn. Người dùng thêm một tác vụ vào đầu danh sách. Điều gì có thể xảy ra và cần sửa thiết kế như thế nào?

*Gợi ý đáp án:* phần tử ở chỉ số 4 có thể đổi; lưu `selectedTaskId` rồi tra cứu ID khi cần sẽ giữ đúng thực thể dù thứ tự mảng đổi.

**Bài 2 — Handle tái sử dụng.** Ô 7 từng chứa A và có thế hệ 3. Sau khi xóa A, ô này được tái sử dụng cho B với thế hệ 4. Handle `(7,3)` có hợp lệ không?

*Đáp án:* không; kiểm tra thế hệ phát hiện stale handle. Cần tránh để thế hệ hữu hạn quay vòng đến 3 trong thời gian handle cũ còn có thể tồn tại.

**Bài 3 — Danh sách và map.** Bạn có danh sách liên kết đôi theo thứ tự truy cập và hash map `id → node`. Khi xóa một nút, chỉ xóa khỏi danh sách nhưng quên xóa khỏi map. Bất biến nào bị phá?

*Đáp án:* map vẫn chứa ID trỏ đến nút đã bị loại khỏi danh sách, có thể là tham chiếu không còn hợp lệ; `get(id)` và kết quả duyệt không còn mô tả cùng tập phần tử.

**Bài 4 — Thứ tự trong heap.** Nếu mảng của min-heap là `[1,3,2,8,7,5]`, liệu duyệt từ trái sang phải có tạo dãy tăng dần không?

*Đáp án:* không; heap chỉ bảo đảm mỗi nút cha có ưu tiên không lớn hơn con. Dãy có phần tử 3 đứng trước 2 nhưng vẫn có thể thỏa bất biến heap.

**Bài 5 — Báo cáo có snapshot.** API trả tác vụ theo `(createdAt,id)` bằng keyset pagination. Có đảm bảo tất cả trang thấy cùng tập tác vụ tại thời điểm đầu tiên không?

*Đáp án:* không. Keyset giảm sai lệch do offset dịch nhưng dữ liệu mới và cập nhật khóa sau cursor vẫn có thể xuất hiện; cần snapshot hoặc cơ chế phiên bản/nhất quán riêng nếu yêu cầu cố định tập kết quả.

**Bài 6 — Đồ thị thay chỉ số.** Đỉnh có ID `U-25` được ánh xạ sang chỉ số 10 trong snapshot A, nhưng thành chỉ số 9 trong snapshot B. Có thể dùng chỉ số 10 từ A để truy cập B không?

*Đáp án:* không, trừ khi có bảo đảm rõ rằng ánh xạ còn giống nhau. Hãy lưu ID logic và ánh xạ qua bảng ID → chỉ số của đúng phiên bản đồ thị.

## Kết luận

**Danh tính**, **tham chiếu** và **thứ tự duyệt** là ba bảo đảm cần thiết kế riêng. ID logic giúp giữ đúng thực thể khi vị trí lưu thay đổi. Handle có thế hệ giúp phát hiện việc tái sử dụng ô, còn tham chiếu/iterator phải tuân thủ quy tắc hợp lệ của container và vòng đời đối tượng. Thứ tự duyệt muốn dự đoán được phải có khóa sắp và quy tắc phá hòa; nếu muốn đọc nhất quán qua nhiều thao tác hoặc nhiều trang, còn cần cơ chế snapshot hay đồng bộ.

Lựa chọn cấu trúc nên bắt đầu từ hợp đồng ổn định, sau đó mới so độ phức tạp của thao tác: mảng cho truy cập vị trí `O(1)`, bảng băm cho tra cứu ID kỳ vọng `O(1)`, cây cân bằng cho thứ tự và cận `O(log n)`, danh sách liên kết cho chỉnh sửa nút đã biết `O(1)`, heap cho cực trị, và đồ thị cần phân biệt ID đỉnh với chỉ số lưu trữ. Khi bất biến được viết rõ và được kiểm chứng sau các thao tác đổi vị trí, xóa, tái sử dụng hay duyệt đồng thời, hệ thống giữ được sự đúng đắn ngay cả khi dữ liệu phát triển và cấu trúc nội bộ thay đổi.
