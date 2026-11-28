# Giới thiệu CAS và yêu cầu về khả năng quan sát thay đổi bộ nhớ

Trong một chương trình nhiều luồng, hai thao tác tưởng như đơn giản là “đọc giá trị hiện tại” và “ghi giá trị mới” có thể bị một luồng khác chen vào giữa. Điều này đặc biệt nguy hiểm khi xây dựng **stack, queue, bảng băm hoặc bộ đếm dùng chung**: mỗi luồng có thể tính toán đúng trên dữ liệu mình vừa đọc, nhưng kết quả cuối cùng lại sai vì dữ liệu đã thay đổi.

**Compare-and-swap (CAS)** là một phép toán nguyên tử giúp thực hiện cập nhật *có điều kiện*: chỉ ghi giá trị mới nếu giá trị hiện tại vẫn bằng giá trị đã quan sát. Tuy nhiên, CAS giải quyết một phần của bài toán đồng thời. Để một luồng đọc được **dữ liệu liên quan đã được luồng khác ghi trước đó**, chương trình còn cần quy tắc về **thứ tự bộ nhớ và khả năng quan sát thay đổi** (*memory visibility*). Bài này giải thích cả hai điều kiện và cách chúng phối hợp trong cấu trúc dữ liệu.

## 1. Vì sao phép gán thông thường chưa đủ?

Giả sử biến đếm dùng chung ban đầu bằng 0, và hai luồng cùng thực hiện:

```text
temp = counter
temp = temp + 1
counter = temp
```

Một cách xen kẽ có thể xảy ra:

| Thời điểm | Luồng A | Luồng B | Giá trị `counter` |
|---|---|---|---|
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1 | | 0 |
| 4 | | Tính 1 | 0 |
| 5 | Ghi 1 | | 1 |
| 6 | | Ghi 1 | 1 |

Đúng ra kết quả phải là 2, nhưng một lần tăng đã bị mất (*lost update*). Phép gán một giá trị có thể là nguyên tử trên một số hệ thống, song **toàn bộ chuỗi đọc → tính → ghi** vẫn không phải một thao tác nguyên tử. Nếu các lượt truy cập dùng biến thường mà không đồng bộ trong ngôn ngữ như C++, chương trình còn có thể mắc **data race**, dẫn đến hành vi không xác định theo mô hình bộ nhớ của ngôn ngữ.

Có thể dùng mutex để bảo vệ toàn bộ đoạn cập nhật. CAS cung cấp một lựa chọn khác: kiểm tra và thay đổi một vị trí nguyên tử trong **cùng một thao tác**.

## 2. CAS hoạt động như thế nào?

CAS nhận ba thông tin:

- **Địa chỉ/vị trí nguyên tử** cần cập nhật, ký hiệu `location`.
- **Giá trị kỳ vọng** `expected`: giá trị mà luồng cho rằng hiện đang lưu ở vị trí đó.
- **Giá trị mới** `desired`: giá trị chỉ được ghi nếu giả định còn đúng.

Ngữ nghĩa trừu tượng:

```text
CAS(location, expected, desired):  // toàn bộ thân là MỘT thao tác nguyên tử
    actual = giá_trị_hiện_tại(location)
    nếu actual == expected:
        location = desired
        trả_về (thành_công, actual)
    ngược_lại:
        trả_về (thất_bại, actual)
```

Các dòng bên trong chỉ là **mô tả hành vi**. Không thể cài CAS đúng bằng một `if` rồi một phép gán trên biến thường: cần primitive nguyên tử do phần cứng, runtime hoặc thư viện đồng thời cung cấp. Một số kiến trúc sử dụng cơ chế khác, chẳng hạn *load-linked/store-conditional* (LL/SC), để thực hiện chức năng tương đương.

Giả sử `counter = 0`. Luồng A và B cùng đọc 0 và đề xuất ghi 1. Một CAS có thể thành công, đổi 0 thành 1. CAS còn lại thấy giá trị hiện tại không còn là 0 nên thất bại; luồng thất bại đọc lại 1 và thử đổi 1 thành 2. Kết quả cuối cùng có thể đạt 2 mà không làm mất một lần tăng.

**Điểm tuyến tính hóa** (*linearization point*) của một lần CAS thành công là thời điểm phép cập nhật nguyên tử có hiệu lực. Các luồng quan sát vị trí đó như thể phép CAS diễn ra không chia nhỏ. Điều này chưa có nghĩa là toàn bộ một thuật toán cập nhật nhiều vị trí đã tuyến tính hóa đúng.

## 3. Vòng lặp CAS: đọc, thử cập nhật và thử lại

Một mẫu thường dùng:

```text
repeat:
    old = atomic_load(location)
    new = f(old)
until CAS(location, old, new) thành_công
```

Nếu có luồng khác đổi `location` sau lần đọc, CAS thất bại. Vòng lặp tính lại `new` từ trạng thái mới; không được cứ mãi ghi giá trị tính từ `old` đã lỗi thời.

Ví dụ dưới đây dùng **C++20** với một bộ đếm độc lập. `std::atomic` cung cấp các thao tác nguyên tử và quy tắc thứ tự bộ nhớ:

```cpp
#include <atomic>
#include <cstdint>

std::atomic<std::uint64_t> counter{0};

void increment() {
    std::uint64_t expected = counter.load(std::memory_order_relaxed);

    while (!counter.compare_exchange_weak(
        expected, expected + 1,
        std::memory_order_relaxed,  // nếu CAS thành công
        std::memory_order_relaxed   // nếu CAS thất bại
    )) {
        // compare_exchange_weak cập nhật expected theo giá trị quan sát.
        // Vòng lặp thử lại với expected vừa được cập nhật.
    }
}
```

Chú ý:

1. `compare_exchange_weak` có thể báo thất bại **giả** (*spurious failure*) ngay cả khi giá trị đang bằng `expected`. Vì vậy, nó thường được dùng trong vòng lặp.
2. Khi CAS thất bại, tham số `expected` được cập nhật thành giá trị quan sát được; lần thử tiếp theo tính `expected + 1` từ giá trị mới ấy.
3. Với bộ đếm chỉ dùng để đếm, không làm tín hiệu công bố dữ liệu khác, `memory_order_relaxed` vẫn đủ để tránh mất cập nhật. Nó **không** thiết lập thứ tự quan sát cho các vùng dữ liệu không liên quan.
4. `uint64_t` là số nguyên không dấu; khi vượt giới hạn, phép cộng sẽ quay vòng theo quy tắc của kiểu này. Nếu bài toán không cho phép quay vòng, cần thiết kế kiểm tra giới hạn.

`compare_exchange_strong` không được phép thất bại giả theo cách của `weak`, nên phù hợp cho một số tình huống chỉ thử một lần. Cả hai vẫn có thể **thất bại thật** khi giá trị đã khác `expected`; dùng `strong` không loại bỏ nhu cầu xử lý tranh chấp.

## 4. Nguyên tử tính không đồng nghĩa với nhìn thấy mọi thay đổi

Hãy phân biệt ba câu hỏi:

| Câu hỏi | Ý nghĩa |
|---|---|
| **Atomicity (nguyên tử tính)** | Một thao tác trên đối tượng nguyên tử có thể bị quan sát như bị thực hiện một nửa hay không? |
| **Visibility (khả năng quan sát)** | Khi thấy tín hiệu từ luồng khác, ta có được bảo đảm nhìn thấy dữ liệu mà luồng đó ghi trước tín hiệu không? |
| **Ordering (thứ tự bộ nhớ)** | Trình biên dịch và CPU được phép sắp xếp/quan sát các thao tác bộ nhớ theo những thứ tự nào? |

Ví dụ, một luồng chuẩn bị một bản ghi rồi công bố cờ `ready = true`; luồng khác đợi `ready` và đọc bản ghi. Nếu không có đồng bộ đúng, việc đọc được cờ chưa đủ để khẳng định bản ghi đã được **công bố an toàn**. Trình biên dịch và CPU có thể tối ưu, sắp xếp lại hoặc lưu đệm các truy cập trong những giới hạn mà mô hình bộ nhớ cho phép.

Trong C++, hai luồng truy cập **cùng một biến thường**, có ít nhất một luồng ghi và không có quan hệ đồng bộ thích hợp, tạo thành *data race* với hành vi không xác định. Đánh dấu biến là `volatile` **không** làm thao tác đó nguyên tử và **không** tạo đồng bộ giữa các luồng trong C++.

Các đối tượng `std::atomic` ngăn data race trên chính đối tượng nguyên tử, nhưng để công bố dữ liệu thường đi kèm, cần một quan hệ **happens-before** (xảy ra-trước) phù hợp.

### Quan hệ happens-before

Nếu trong luồng A:

```text
ghi payload
  ↓ thứ tự trong cùng luồng
công bố ready bằng thao tác release
```

và trong luồng B:

```text
đọc ready bằng thao tác acquire, quan sát lần công bố
  ↓ thứ tự trong cùng luồng
đọc payload
```

thì thao tác **release** ở A *synchronizes-with* thao tác **acquire** ở B, khi acquire đọc giá trị của lần release đó (hoặc từ chuỗi release hợp lệ theo mô hình bộ nhớ). Từ quan hệ này, việc ghi payload xảy ra-trước việc đọc payload; các giá trị đã chuẩn bị có thể được sử dụng an toàn nếu không có lần ghi tranh chấp khác.

Lưu ý: release/acquire nói về **bảo đảm ngữ nghĩa bộ nhớ**. Nó không hứa một luồng đang bận chờ sẽ được lên lịch ngay hay sẽ nhìn thấy giá trị mới trong một số nanôgiây cố định.

## 5. Các mức thứ tự bộ nhớ thường gặp

Trong C++, ngoài kiểu nguyên tử, mỗi thao tác có thể mang yêu cầu về *memory ordering*:

| Thứ tự | Bảo đảm chính | Ví dụ thường dùng |
|---|---|---|
| `relaxed` | Thao tác vẫn nguyên tử; không tạo đồng bộ thứ tự đối với dữ liệu khác | Bộ đếm thống kê độc lập |
| `release` | Các thao tác ghi trước đó trong luồng được công bố cho luồng thực hiện acquire phù hợp | Công bố một bản ghi đã khởi tạo |
| `acquire` | Các thao tác sau acquire được đặt đúng sau việc quan sát một công bố release phù hợp | Đọc bản ghi sau khi thấy cờ sẵn sàng |
| `acq_rel` | Kết hợp acquire và release cho thao tác đọc-sửa-ghi nguyên tử | CAS vừa nhận trạng thái cũ vừa công bố trạng thái mới |
| `seq_cst` | Ngoài bảo đảm acquire/release liên quan, các thao tác tuần tự nhất quán có thể được xem trong một thứ tự tổng toàn cục thống nhất | Lựa chọn mặc định dễ lý giải cho nhiều ví dụ đơn giản |

`seq_cst` là thứ tự mạnh nhất trong nhóm trên, nhưng **không tự biến một giao thức nhiều biến thành đúng**. Phải tiếp tục xác định ai ghi, ai đọc, thao tác nào công bố dữ liệu và bất biến của cấu trúc dữ liệu.

Với `compare_exchange_weak/strong` trong C++, ta có thể chỉ định một thứ tự khi **thành công** và một thứ tự khi **thất bại**. Nhánh thất bại không thực hiện ghi, nên thứ tự thất bại không được là `release` hoặc `acq_rel`; nó cũng không được mạnh hơn thứ tự thành công theo các ràng buộc của API.

## 6. Ví dụ CAS kết hợp release/acquire để công bố dữ liệu

Đây là mô hình **một luồng ghi, một hoặc nhiều luồng đọc, công bố đúng một lần**. Luồng ghi chuẩn bị `payload` rồi dùng CAS chuyển cờ nguyên tử từ `false` sang `true`.

```cpp
#include <atomic>
#include <cassert>

int payload = 0;                     // Dữ liệu thường
std::atomic<bool> ready{false};      // Cờ công bố nguyên tử

void producer() {                     // Chỉ một producer gọi hàm này
    payload = 42;                     // (1) Chuẩn bị dữ liệu

    bool expected = false;
    bool published = ready.compare_exchange_strong(
        expected, true,
        std::memory_order_release,    // (2) Công bố khi CAS thành công
        std::memory_order_relaxed     // Không ghi nếu CAS thất bại
    );
    assert(published);                // Ví dụ chỉ công bố một lần
}

int consumer() {
    while (!ready.load(std::memory_order_acquire)) {
        // Đợi tín hiệu (minh họa; vòng chờ thực tế cần cân nhắc).
    }
    return payload;                   // (3) Đọc sau khi thấy ready=true
}
```

Vì CAS thành công ở (2) là **release** và phép `load` ở consumer đọc `true` bằng **acquire**, ghi `payload = 42` ở (1) xảy ra-trước lần đọc ở (3). Dù `payload` là biến thường, ví dụ này không có data race nếu producer chỉ ghi trước khi công bố và không có luồng khác tiếp tục sửa `payload`.

Nếu thay cả hai thứ tự bằng `relaxed`, cờ vẫn nguyên tử nhưng thiếu quan hệ công bố dữ liệu thường. Nếu `ready` là biến `bool` thường được đọc và ghi không đồng bộ, chương trình C++ gặp data race. Đó là lý do **CAS nguyên tử phải đi cùng thứ tự bộ nhớ đúng với mục tiêu giao tiếp giữa các luồng**.

CAS trong ví dụ một producer chỉ nhằm minh họa thao tác công bố có điều kiện; thao tác `ready.store(true, std::memory_order_release)` cũng đủ nếu chắc chắn chỉ một producer được phép công bố. Muốn tái sử dụng vùng dữ liệu để công bố **nhiều lần**, cần một giao thức riêng tránh ghi đè khi consumer vẫn đang đọc. Đoạn mã trên không phải một hàng đợi có thể tái sử dụng.

## 7. CAS trong stack dùng chung

Với **stack**, trạng thái quan trọng thường là con trỏ `top` trỏ đến nút đầu. Một phương án không khóa dùng CAS để thay `top` nguyên tử.

### Ý tưởng push

```text
push(node):
    lặp:
        old = atomic_load(top)
        node.next = old
    cho đến khi CAS(top, old, node) thành công
```

Nếu luồng khác đổi `top` giữa `atomic_load` và CAS, thao tác thất bại, nút mới nối lại theo `top` cập nhật rồi thử tiếp. Nếu CAS thành công, phép thay `top` là điểm tuyến tính hóa của `push` **khi triển khai đầy đủ đúng bất biến và thứ tự bộ nhớ**.

Mã trên chỉ trình bày **ý tưởng thuật toán**, chưa chỉ định cách quản lý vòng đời nút và thứ tự bộ nhớ. Trong triển khai thực, `push` cần công bố các trường của nút bằng thứ tự phù hợp (thường là release trên CAS thành công), còn `pop` cần đọc nút theo acquire và giải quyết vấn đề nút có thể bị gỡ hoặc giải phóng bởi luồng khác.

### ABA: địa chỉ giống nhau không có nghĩa trạng thái không thay đổi

Giả sử stack ban đầu:

```text
top -> A -> B -> C
```

Một luồng T1 đọc `top = A` và `next = B`, chuẩn bị CAS đổi `top` từ A sang B. Trước khi CAS, T2 gỡ A, gỡ B rồi đưa **chính nút A** trở lại đầu stack:

```text
top -> A -> C
```

T1 thấy `top` vẫn có giá trị địa chỉ A nên CAS `A -> B` có thể **thành công**, dù B đã bị gỡ và có thể bị giải phóng. Kết quả có thể làm hỏng liên kết hoặc dẫn tới truy cập bộ nhớ không còn hợp lệ. Đây là hiện tượng **ABA**: trạng thái đã đi từ A sang trạng thái khác rồi trở lại A, khiến phép so sánh giá trị đơn lẻ không nhận ra lịch sử thay đổi.

Một số kỹ thuật xử lý:

- **Con trỏ kèm phiên bản (tagged/versioned pointer):** CAS so sánh cả con trỏ và số phiên bản. Cần đủ bit và xử lý khả năng phiên bản quay vòng.
- **Hazard pointers hoặc epoch-based reclamation:** kiểm soát khi nào nút đã gỡ có thể được thu hồi để luồng khác không còn đọc vùng nhớ bị giải phóng.
- **Thu gom rác (garbage collection):** hỗ trợ an toàn vòng đời đối tượng, nhưng không tự giải quyết mọi lỗi ABA về mặt logic của thuật toán.

Các cơ chế quản lý vòng đời và cơ chế phát hiện ABA giải quyết những khía cạnh liên quan nhưng **không hoàn toàn thay thế lẫn nhau**. Không nên sao chép giả mã `pop` không khóa để dùng trong C/C++ khi chưa có chiến lược bảo vệ nút và chứng minh tính đúng.

## 8. CAS có đồng nghĩa lock-free không?

CAS thường được dùng để xây dựng thuật toán **non-blocking**, nhưng việc sử dụng CAS không tự bảo đảm thuật toán sẽ *lock-free* hoặc *wait-free*.

| Khái niệm | Ý nghĩa bảo đảm tiến triển |
|---|---|
| **Blocking (có khóa/chờ)** | Luồng có thể phải chờ luồng khác thả mutex hoặc giải phóng tài nguyên. |
| **Lock-free** | Trong quá trình thực thi liên tục có bước tiến, hệ thống bảo đảm một thao tác nào đó sẽ hoàn thành; một luồng cụ thể vẫn có thể bị đói tài nguyên. |
| **Wait-free** | Mỗi thao tác của từng luồng hoàn thành sau một số bước hữu hạn có chặn trên theo mô hình đã xét. |

Khi nhiều luồng tranh chấp cùng vị trí nguyên tử, một luồng có thể phải lặp CAS nhiều lần. Do vậy, **mỗi lần thử CAS** có thể là thao tác hằng số trong mô hình máy, nhưng **toàn bộ vòng lặp** không có bảo đảm thời gian $O(1)$ trong trường hợp xấu nhất dưới tranh chấp tùy ý.

Một vòng lặp CAS ngắn không gọi khóa ngoài và có cấu trúc đúng có thể là phần cốt lõi của thuật toán lock-free. Ngược lại, nếu vòng lặp CAS phụ thuộc thao tác có khóa, cấp phát có chờ hoặc giao thức không bảo đảm tiến triển, ta không thể kết luận toàn thuật toán lock-free chỉ từ cú pháp CAS. Ngoài ra, ngay cả primitive `std::atomic<T>` cũng không phải lúc nào được triển khai bằng lệnh phần cứng không khóa cho mọi kiểu `T`; có thể kiểm tra khả năng này bằng `is_lock_free()`.

**Chi phí thực tế:** nhiều lần CAS thất bại làm tăng lưu lượng đồng bộ cache, tranh chấp một cache line và thời gian CPU. Những kỹ thuật như giảm chia sẻ trạng thái, phân vùng dữ liệu, backoff có kiểm soát hoặc sử dụng queue chuyên dụng đôi khi hữu ích hơn việc thêm nhiều vòng lặp CAS.

## 9. Phân biệt CAS, volatile, mutex và atomic increment

| Cơ chế | Bảo đảm chính | Giới hạn cần nhớ |
|---|---|---|
| Biến thường | Đọc/ghi trong điều kiện không có data race | Truy cập đồng thời xung đột cần đồng bộ |
| `volatile` trong C++ | Phục vụ một số truy cập có tác dụng phụ bên ngoài mô hình luồng thông thường | Không tạo atomicity hay happens-before giữa các luồng |
| `std::atomic<T>` | Truy cập nguyên tử và các tùy chọn memory ordering | Không tự bảo vệ bất biến trải trên nhiều đối tượng |
| CAS | Cập nhật có điều kiện một đối tượng nguyên tử | Có thể thất bại, cần retry và xử lý ABA nếu liên quan |
| `fetch_add` nguyên tử | Tăng/giảm bộ đếm trực tiếp bằng read-modify-write nguyên tử | Không thay thế một giao thức cập nhật nhiều trường |
| Mutex | Vùng tới hạn và đồng bộ bộ nhớ khi khóa/mở khóa đúng cách | Có thể gây chờ, tranh chấp và deadlock nếu sử dụng sai |

Trong **Java**, `AtomicInteger.compareAndSet` hoặc `AtomicReference.compareAndSet` là API CAS quen thuộc; các phương thức `compareAndSet` này có ngữ nghĩa đồng bộ tương ứng với truy cập volatile của Java. Tuy nhiên, Java `volatile` chỉ giúp đảm bảo tính quan sát và thứ tự phù hợp cho các truy cập, **không** biến biểu thức `count++` thành phép tăng nguyên tử. C++ và Java có quy tắc riêng nên không được mang ý nghĩa của từ khóa `volatile` từ ngôn ngữ này sang ngôn ngữ kia.

## 10. Quy trình kiểm tra một thiết kế dùng CAS

Trước khi dùng CAS cho một cấu trúc dữ liệu đồng thời, hãy trả lời các câu hỏi:

1. **Trạng thái nào cần cập nhật nguyên tử?** CAS chỉ thay đổi một đối tượng nguyên tử (hoặc một biểu diễn nguyên tử có đủ độ rộng). Nếu bất biến trải qua nhiều trường, cần giao thức đảm bảo sự nhất quán của toàn bộ trạng thái.
2. **Điểm tuyến tính hóa ở đâu?** Xác định thao tác CAS thành công nào được xem là thời điểm `push`, `pop`, `insert` hoặc `remove` có hiệu lực.
3. **Ai công bố dữ liệu, ai quan sát?** Ghi rõ thao tác release và acquire tương ứng. Phân biệt trường hợp chỉ cần `relaxed` với trường hợp phải đồng bộ payload.
4. **Nếu CAS thất bại thì sao?** Cập nhật `expected`, tính lại kết quả và thử lại; tránh dùng trạng thái lỗi thời. Với `weak`, chấp nhận khả năng thất bại giả.
5. **Nút bị gỡ sẽ sống bao lâu?** Đánh giá ABA, truy cập sau giải phóng, cơ chế thu hồi bộ nhớ và khả năng tái sử dụng địa chỉ.
6. **Bảo đảm tiến triển là gì?** Chứng minh các mức blocking, lock-free hay wait-free theo toàn thuật toán; đo tác động của tranh chấp và số lần retry.

Trong kiểm thử, cần chạy những tình huống nhiều luồng cố ý chen vào giữa bước đọc và bước CAS, kiểm tra tính đúng theo lịch sử thao tác (linearizability), dùng công cụ phát hiện data race khi phù hợp và kiểm tra dưới tải tranh chấp. Một lần chạy đúng không chứng minh thuật toán đồng thời luôn đúng; nhiều lỗi chỉ xuất hiện ở một thứ tự xen kẽ hiếm.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Hai luồng cùng muốn đổi `counter` từ 7 thành 8 bằng CAS với `expected = 7`. Cả hai có thể thành công không?

**Đáp án:** Không, nếu không có thao tác trung gian nào đưa giá trị trở lại 7. Một CAS thành công đổi 7 thành 8; CAS còn lại quan sát giá trị khác 7 nên thất bại. Luồng thất bại phải lấy trạng thái mới trước khi thử tiếp.

**Câu 2.** Vì sao `compare_exchange_weak` thường nằm trong vòng lặp?

**Đáp án:** Ngoài thất bại do luồng khác thay đổi giá trị, nó có thể thất bại giả. Vòng lặp xử lý cả hai trường hợp và dùng giá trị `expected` vừa được cập nhật.

**Câu 3.** Một producer ghi `payload` rồi `ready.store(true, relaxed)`; consumer đợi `ready.load(relaxed)` trả về `true` rồi đọc `payload` thường. Đã đủ bảo đảm an toàn chưa?

**Đáp án:** Chưa. Cặp truy cập `relaxed` không tạo quan hệ synchronizes-with cho các truy cập `payload` thường. Cần giao thức công bố release/acquire (hoặc đồng bộ tương đương), và cần ngăn producer ghi lại `payload` trong lúc consumer đọc.

**Câu 4.** CAS so sánh `top == A` có nhận ra `top` đã thay từ A sang B rồi trở lại A không?

**Đáp án:** Không. CAS chỉ so sánh giá trị đang thấy với kỳ vọng; việc trạng thái đã đi qua một giá trị khác chính là nguy cơ ABA. Tùy thuật toán cần version tag, quy tắc vòng đời nút hoặc biện pháp khác.

**Câu 5.** Dùng CAS có luôn nhanh hơn mutex không?

**Đáp án:** Không. CAS có thể phải thử lại nhiều lần khi tranh chấp; mutex có thể phù hợp hơn nếu vùng tới hạn lớn hoặc cần cập nhật nhiều đối tượng. Hãy xét cả tính đúng, tiến triển, bộ nhớ và hiệu năng thực tế.

CAS cho phép nhiều luồng **thử cập nhật một trạng thái chung mà không làm mất thay đổi đã xảy ra ở giữa**. Để xây dựng một cấu trúc dữ liệu dùng chung an toàn, còn phải bảo đảm dữ liệu được **công bố và quan sát đúng thứ tự**, các nút không bị thu hồi quá sớm, bất biến được giữ trong mọi cách xen kẽ và vòng lặp cập nhật có đặc tính tiến triển phù hợp. Nắm được những điều kiện ấy là nền tảng trước khi học stack, queue và các cấu trúc không khóa phức tạp hơn.
