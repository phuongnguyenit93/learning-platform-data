# Tag, tập tag và mức chi tiết

Unified JVM Logging gắn mỗi log message nội bộ của JVM với một **tag set** mô tả thành phần hoặc hoạt động phát sinh message. Khi cấu hình bằng `-Xlog`, ta chọn tag set cần quan sát và giới hạn mức chi tiết bằng một **log level**. Hai phần này quyết định message nào được phát ra; output và decorators là các phần cấu hình riêng.

Điểm quan trọng nhất khi đọc tag selection là phân biệt ba toán tử: dấu `+` yêu cầu một tổ hợp tag, dấu phẩy `,` tách các selection độc lập, còn wildcard `*` cho phép match tag set có thêm tag ngoài những tag đã chỉ định. Nếu bỏ wildcard, JVM chỉ match đúng tag set được nêu. Mức log là ngưỡng tích lũy: chọn `info` sẽ nhận `error`, `warning` và `info`; chọn `debug` nhận thêm `debug`; chọn `trace` nhận cả các message chi tiết nhất.

## Mục tiêu

- Hiểu tag và tag set trong Unified JVM Logging.
- Phân biệt tag đơn với tổ hợp nhiều tag.
- Đọc đúng ý nghĩa của `+`, `,`, `*` và `all`.
- Hiểu matching chính xác khi không có wildcard.
- Chọn log level theo ngưỡng chi tiết tích lũy.
- Kết hợp nhiều selection với level riêng.
- Dùng `off` để tắt một nhóm log cụ thể.
- Chọn tag phù hợp cho GC, class loading, safepoint và các hoạt động JVM.
- Kiểm tra tag/level có sẵn trên runtime thực tế.
- Tránh bật log quá rộng hoặc quá chi tiết trong môi trường production.

## 1. Tag và tag set

JVM phát sinh log message tại các điểm ghi log nội bộ. Mỗi message được gắn một hoặc nhiều tag. Tag là nhãn phân loại hoạt động, ví dụ `gc` cho garbage collection hoặc `class` cho hoạt động liên quan class.

Một message có thể mang một tag hoặc một tag set gồm nhiều tag. Ví dụ:

| Tag set minh họa | Nhóm hoạt động |
| --- | --- |
| `gc` | Sự kiện garbage collection có tag `gc` |
| `safepoint` | Hoạt động safepoint |
| `class+load` | Hoạt động nạp class |
| `class+init` | Khởi tạo class |
| `gc+heap` | Thông tin GC liên quan heap |
| `gc+ref` | Xử lý reference trong quá trình GC |

Trong output, tag set thường được hiển thị trong phần decorators, ví dụ `[info][class,load]`. Cú pháp cấu hình dùng dấu `+` để viết tổ hợp tương ứng: `class+load`.

Tag không phải một cây phân cấp cố định. Không nên giả định tag `class` tự động bao gồm mọi message có `class` cùng tag khác. Việc một selection có match hay không phụ thuộc quy tắc exact/wildcard ở phần tiếp theo.

## 2. Cấu trúc một tag selection

Phần `what` của `-Xlog` dùng dạng tổng quát:

~~~text
tag1[+tag2...][*][=level]
~~~

Ý nghĩa:

- `tag1`: tag bắt buộc trong selection.
- `+tag2...`: yêu cầu thêm một hoặc nhiều tag để tạo tag set.
- `*`: wildcard, cho phép tag set có thêm tag khác ngoài những tag được chỉ định.
- `=level`: ngưỡng log level cho selection đó; nếu bỏ qua, mặc định là `info`.

Ví dụ:

~~~text
-Xlog:gc=info
-Xlog:gc+heap=debug
-Xlog:class+load*=info
~~~

Selection thứ nhất chọn tag set chính xác `gc` ở ngưỡng `info`. Selection thứ hai yêu cầu cả `gc` và `heap`, ở ngưỡng `debug`. Selection thứ ba yêu cầu tag set có `class` và `load`, đồng thời cho phép có thêm tag khác vì có `*`.

## 3. Exact matching khi không có wildcard

Đây là quy tắc dễ gây nhầm lẫn nhất: **nếu không chỉ định `*`, chỉ những message có đúng tag set được chỉ định mới match**.

Ví dụ:

~~~text
-Xlog:gc=info
~~~

Selection này match message có tag set chính xác là `gc`. Message có tag set `gc+heap` hoặc `gc+ref` không tự động match chỉ vì chúng có chứa tag `gc`.

Tương tự:

~~~text
-Xlog:class+load=info
~~~

Selection này match đúng tag set `class+load`. Nếu một message có tag set `class+load+unload`, message đó không match selection exact này vì tag set còn có tag bổ sung.

Quy tắc exact giúp cấu hình hẹp và có thể dự đoán được. Khi chỉ muốn một nhóm message cụ thể, hãy bắt đầu bằng selection không có wildcard.

## 4. Wildcard (*) và matching tag set mở rộng

Wildcard cho phép match mọi tag set có chứa các tag đã nêu, kể cả khi message còn mang tag bổ sung.

~~~text
-Xlog:gc*=info
~~~

Selection này match tag set `gc`, `gc+heap`, `gc+ref` và các tổ hợp khác có chứa `gc` nếu runtime phát ra chúng.

Ví dụ:

~~~text
-Xlog:class+load*=info
-Xlog:gc+heap*=debug
~~~

Selection đầu tiên match các tag set có cả `class` và `load`, kể cả khi có thêm tag khác. Selection thứ hai yêu cầu cả `gc` và `heap`, cho phép các tag bổ sung và chỉ nhận tới level `debug`.

Wildcard không có nghĩa là bật mọi tag của JVM. `gc*` vẫn giới hạn vào các tag set chứa `gc`; muốn chọn mọi tag set, dùng `all`.

### 4.1. So sánh exact và wildcard

| Selection | Tag set được match |
| --- | --- |
| `gc=info` | Chỉ `{gc}` |
| `gc*=info` | Mọi tag set có chứa `gc` |
| `gc+heap=debug` | Chỉ `{gc, heap}` |
| `gc+heap*=debug` | Mọi tag set có cả `gc` và `heap`, có thể có tag khác |
| `class+load=info` | Chỉ `{class, load}` |
| `class+load*=info` | Mọi tag set có cả `class` và `load` |

Chọn wildcard khi muốn theo dõi cả nhóm tag set liên quan. Wildcard thường tạo nhiều log hơn selection exact, vì vậy nên đánh giá lượng log trước khi bật trong production.

## 5. Dấu cộng (+): yêu cầu tag kết hợp

Dấu `+` biểu thị các tag phải cùng xuất hiện trong tag set của message.

~~~text
-Xlog:gc+ref=debug
~~~

Selection này yêu cầu message có cả tag `gc` và `ref`. Nó không có nghĩa là chọn message mang `gc` hoặc message mang `ref`.

Ví dụ khác:

~~~text
-Xlog:class+load=info
-Xlog:class+init=info
-Xlog:gc+heap=debug
-Xlog:gc+safepoint=info
~~~

Tag combination có thể gồm nhiều hơn hai tag. Mỗi tag bổ sung làm selection cụ thể hơn nếu không có wildcard.

Không dùng `+` để thay cho dấu phẩy khi muốn chọn nhiều nhóm độc lập. `gc+ref` là yêu cầu cả hai tag; `gc,ref` là hai selection riêng.

## 6. Dấu phẩy (,): nhiều selection độc lập

Dấu phẩy phân tách nhiều tag selection. Một message được xét theo từng selection; các selection không được gộp thành một tag set mới.

~~~text
-Xlog:gc=info,safepoint=info
~~~

Cấu hình này chọn:

- Message có tag set chính xác `gc` ở level `info` trở xuống theo ngưỡng đã chọn.
- Message có tag set chính xác `safepoint` ở cùng ngưỡng.

Message có tag set `{gc, safepoint}` không match hai selection exact riêng lẻ trên. Nếu muốn chọn đúng tag set gồm cả hai tag, dùng:

~~~text
-Xlog:gc+safepoint=info
~~~

Nếu muốn chọn cả các tag set có `gc` và tag set có `safepoint`, kể cả khi có tag bổ sung, dùng:

~~~text
-Xlog:gc*=info,safepoint*=info
~~~

### 6.1. Mỗi selection có thể có level riêng

~~~text
-Xlog:gc=debug,safepoint=info,class+load=warning
~~~

Ở đây mỗi nhóm có ngưỡng riêng:

- `gc=debug`: GC message tới `debug`.
- `safepoint=info`: safepoint message tới `info`.
- `class+load=warning`: class-load message chỉ ở `warning` và `error`.

Đặt level ngay sau selection tương ứng để tránh hiểu nhầm level áp dụng cho toàn bộ chuỗi.

## 7. Tag all và selection toàn bộ

`all` là từ khóa đặc biệt dùng để match mọi tag combination:

~~~text
-Xlog:all=info
~~~

Selection này bật mọi tag set ở ngưỡng `info` và các level nghiêm trọng hơn. Nó hữu ích khi cần khảo sát rộng trong môi trường thử nghiệm, nhưng có thể tạo lượng log lớn.

Không đồng nghĩa với việc `all` là một tag thông thường có thể kết hợp như `gc+all`. Hãy dùng đúng vai trò đặc biệt của `all` trong tag selection.

Để tắt toàn bộ cấu hình logging đã có, có thể dùng `-Xlog:disable`; đây là tùy chọn điều khiển cấu hình tổng thể, không phải tag set. Sau đó có thể thêm selection cụ thể mà mình cần. Chỉ dùng khi muốn chủ động thay toàn bộ cấu hình, vì thao tác này cũng tắt các cấu hình mặc định.

## 8. Log level và ngưỡng chi tiết

Unified Logging có các level:

| Level | Ý nghĩa |
| --- | --- |
| `off` | Không ghi message của selection |
| `error` | Lỗi |
| `warning` | Cảnh báo |
| `info` | Thông tin vận hành |
| `debug` | Chi tiết phục vụ chẩn đoán |
| `trace` | Chi tiết sâu nhất |

Thứ tự tăng dần về độ chi tiết là:

~~~text
off < error < warning < info < debug < trace
~~~

Trong cấu hình, level được chọn là ngưỡng tối đa về độ chi tiết. JVM ghi message ở level đó và các level nghiêm trọng hơn.

| Selection | Message được nhận |
| --- | --- |
| `gc=error` | `error` |
| `gc=warning` | `error`, `warning` |
| `gc=info` | `error`, `warning`, `info` |
| `gc=debug` | `error`, `warning`, `info`, `debug` |
| `gc=trace` | Tất cả level, gồm `trace` |
| `gc=off` | Không message nào từ selection |

Ví dụ:

~~~text
-Xlog:gc=warning
~~~

Cấu hình này phù hợp khi chỉ cần cảnh báo và lỗi liên quan GC. Nếu đặt `gc=debug`, JVM ghi thêm thông tin chi tiết hơn; lượng log có thể tăng đáng kể.

### 8.1. Level mặc định

Nếu không ghi `=level`, mức mặc định là `info`:

~~~text
-Xlog:gc
~~~

Tương đương với:

~~~text
-Xlog:gc=info
~~~

Không nên giả định mặc định của mọi framework logging là giống Unified Logging. Các mức `FINE`, `DEBUG`, `INFO` trong framework ứng dụng là hệ quy chiếu khác; ở đây ta đang nói riêng về level của JVM Unified Logging.

### 8.2. Tắt một selection bằng off

Có thể tắt một nhóm trong cấu hình nhiều selection:

~~~text
-Xlog:gc*=info,safepoint*=off
~~~

Ở ví dụ này, các tag set có `gc` được chọn ở mức `info`; các tag set có `safepoint` được đặt `off`. `off` hữu ích khi muốn loại một nhóm khỏi cấu hình rộng hơn. Hãy đọc toàn bộ selection để tránh bật một nhóm rồi vô tình tắt nhóm giao nhau.

## 9. Các tag thường gặp trong chẩn đoán JVM

Danh sách tag cụ thể phụ thuộc phiên bản, build và implementation JVM. Một số tag thường gặp trên HotSpot:

| Tag | Nhóm thông tin |
| --- | --- |
| `gc` | Garbage collection |
| `heap` | Heap và thông tin liên quan heap |
| `ref` | Xử lý reference |
| `safepoint` | Safepoint và các điểm dừng phối hợp |
| `class` | Hoạt động liên quan class |
| `load` | Nạp class hoặc thành phần |
| `init` | Khởi tạo class hoặc thành phần |
| `jit` | Biên dịch Just-In-Time |
| `os` | Tương tác với hệ điều hành |
| `container` | Nhận diện/quan sát container trên runtime hỗ trợ |
| `metaspace` | Quản lý metaspace |
| `exceptions` | Thông tin exception ở tầng JVM |

Ví dụ lựa chọn:

~~~text
-Xlog:gc=info
-Xlog:gc+heap=debug
-Xlog:gc+ref=debug
-Xlog:safepoint=info
-Xlog:class+load=info
-Xlog:class+init=info
-Xlog:jit=debug
~~~

Đây là ví dụ tag selection, không phải cam kết rằng mọi tag hoặc mọi tổ hợp có message ở mọi phiên bản. Nếu một selection không có message trên workload hiện tại, điều đó không chứng minh tag không tồn tại; có thể đơn giản là chưa có sự kiện phù hợp.

## 10. Chọn tag và level theo câu hỏi chẩn đoán

Không nên bắt đầu bằng cách bật tất cả log. Hãy xác định câu hỏi cần trả lời rồi chọn selection hẹp:

| Câu hỏi | Selection khởi đầu |
| --- | --- |
| JVM đang thực hiện GC nào? | `gc=info` |
| Cần thêm chi tiết heap trong GC? | `gc+heap=debug` |
| Muốn xem hoạt động reference trong GC? | `gc+ref=debug` |
| Cần điều tra safepoint? | `safepoint=info` |
| Cần xem class được nạp? | `class+load=info` |
| Cần xem class initialization? | `class+init=info` |
| Cần thêm tag con liên quan một nhóm? | Dùng wildcard như `gc*=info` sau khi xác định phạm vi |

Quy trình thực tế:

1. Bật level thấp nhất đủ để quan sát vấn đề.
2. Chạy workload tái hiện lỗi.
3. Kiểm tra tag set xuất hiện trong output.
4. Nếu thiếu chi tiết, tăng level hoặc mở rộng wildcard có kiểm soát.
5. Khi có đủ dữ liệu, giảm level hoặc tắt selection chẩn đoán.

## 11. Kiểm tra tag và level trên runtime

Tag và tag set không nên được xem là danh sách bất biến cho mọi JDK. Kiểm tra trực tiếp:

~~~text
java -Xlog:help
~~~

Lệnh này hiển thị:

- Cú pháp tag selection.
- Các level được hỗ trợ.
- Các decorators.
- Danh sách tag có sẵn trên runtime đó.
- Tag set được mô tả và ví dụ cấu hình.

Trong môi trường triển khai, hãy chạy `java -Xlog:help` bằng đúng binary Java mà ứng dụng sử dụng. Không suy luận tag availability từ máy developer nếu production dùng một build/vendor khác.

Để kiểm tra version:

~~~text
java -version
~~~

`-Xlog` là cơ chế Unified Logging của HotSpot được đưa vào JDK 9. Khi dùng một JVM implementation khác, cần kiểm tra tùy chọn và tài liệu tương ứng.

## 12. Ví dụ Java 9 chạy được

Chương trình nhỏ dưới đây nạp một nested class và in một dòng ứng dụng. JVM class-loading log được cấu hình bằng `-Xlog`; log JVM và output ứng dụng cùng có thể xuất hiện trong stdout, nhưng được phân biệt bằng tag/decorator.

**Tệp:** `TagLevelDemo.java`

~~~java
public class TagLevelDemo {
    static final class LoadedType {
    }

    public static void main(String[] args) {
        new LoadedType();
        System.out.println("application started");
    }
}
~~~

Biên dịch với API Java 9:

~~~text
javac --release 9 TagLevelDemo.java
~~~

Chạy với selection exact cho tag set `class+load`:

~~~text
java -Xlog:class+load=info:stdout:uptime,level,tags TagLevelDemo
~~~

Ví dụ các dòng có thể thấy:

~~~text
[0.031s][info][class,load] TagLevelDemo$LoadedType source: file:/.../
application started
~~~

Thời gian, đường dẫn và các dòng class khác phụ thuộc lần chạy. Dòng `application started` là output do chương trình in; dòng có `[class,load]` là JVM log.

Thử wildcard:

~~~text
java -Xlog:class+load*=info:stdout:uptime,level,tags TagLevelDemo
~~~

Wildcard cho phép match các tag set có cả `class` và `load` kể cả khi có thêm tag khác. Trên một workload cụ thể, output có thể trông giống selection exact nếu không có message bổ sung; semantics của wildcard vẫn rộng hơn.

Thử giảm ngưỡng:

~~~text
java -Xlog:class+load=warning:stdout:uptime,level,tags TagLevelDemo
~~~

Ở ngưỡng `warning`, các message `info` như class-load thông thường không được ghi. Dòng `application started` vẫn xuất hiện vì đó là `System.out.println()` của ứng dụng, không chịu ảnh hưởng bởi level JVM logging.

## 13. Phân biệt tag selection với output và decorators

Tag và level trả lời câu hỏi **message nào được chọn**. Output và decorators trả lời hai câu hỏi khác:

| Phần cấu hình | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Tag selection | Message thuộc nhóm nào? | `gc+heap` |
| Level | Cần mức chi tiết tới đâu? | `=debug` |
| Output | Ghi message ở đâu? | `stdout`, `stderr`, `file=gc.log` |
| Decorators | Hiển thị metadata nào? | `uptime,level,tags` |

Ví dụ đầy đủ:

~~~text
-Xlog:gc+heap=debug:file=logs/heap.log:uptime,pid,level,tags
~~~

Ở đây `gc+heap=debug` là tag/level selection; `file=logs/heap.log` là output; phần cuối là decorators. Việc thay output không thay đổi message được chọn, và việc thêm decorator không làm selection rộng hơn.

## 14. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `gc` tự bao gồm `gc+heap` | Không có wildcard thì match exact tag set | Dùng `gc*` nếu muốn các tag set có thêm tag |
| Dùng `gc+ref` để chọn `gc` hoặc `ref` | Dấu `+` yêu cầu cả hai tag | Dùng `gc,ref` cho hai selection độc lập |
| Dùng `gc,heap` để chọn tag set `gc+heap` | Dấu phẩy tạo hai selection riêng | Dùng `gc+heap` |
| Nghĩ `gc+heap*` và `gc+heap` giống nhau | Wildcard mở rộng matching tới tag set có tag bổ sung | Bỏ `*` nếu chỉ cần exact set |
| Nghĩ `gc=info` chỉ ghi đúng level info | Level là ngưỡng tích lũy | `info` còn nhận `warning` và `error` |
| Bật `trace` trong production mà không giới hạn | Log có thể rất lớn và tăng I/O | Chọn tag hẹp, tăng level có thời hạn |
| Không ghi level và tưởng mặc định là debug | Mặc định của selection là info | Ghi rõ `=debug` khi cần chi tiết hơn |
| Dùng tag không có trên runtime | Tag set thay đổi theo JDK/build | Kiểm tra `java -Xlog:help` trên máy đích |
| Dùng wildcard quá rộng | Có thể thu thập nhiều message không cần thiết | Ưu tiên exact selection, mở rộng dần |
| Nhầm tag JVM với logger ứng dụng | `-Xlog` điều khiển log nội bộ JVM | Dùng logging framework cho log nghiệp vụ |
| Nhầm output với selection | Chọn stdout không làm thay đổi tag match | Xem riêng từng phần trong cú pháp `-Xlog` |

## 15. Quy tắc thực hành

1. Xác định câu hỏi chẩn đoán trước khi chọn tag.
2. Dùng exact matching khi chỉ cần một tag set cụ thể.
3. Dùng `*` khi cần tất cả tag set có chứa các tag đã chỉ định.
4. Dùng `+` để yêu cầu nhiều tag cùng xuất hiện.
5. Dùng dấu phẩy để tạo nhiều selection độc lập; đặt level riêng nếu cần.
6. Nhớ level là ngưỡng tích lũy: level càng chi tiết thì càng nhận thêm message.
7. Bắt đầu với `info` hoặc `warning`; chỉ tăng `debug`/`trace` khi có lý do.
8. Dùng `off` để loại selection không cần thiết khỏi cấu hình.
9. Dùng `all` chỉ khi thực sự cần mọi tag combination.
10. Kiểm tra tag set và level bằng `java -Xlog:help` trên runtime đích.
11. Quan sát lượng log và I/O trong workload thật.
12. Tắt hoặc thu hẹp cấu hình chẩn đoán sau khi hoàn tất điều tra.

## 16. Tự kiểm tra

- Tag là gì? Nhãn phân loại log message nội bộ JVM.
- Tag set là gì? Tập tag gắn với một message.
- `gc+heap` có nghĩa gì? Message phải mang cả hai tag.
- `gc,heap` có nghĩa gì? Hai selection độc lập cho tag set `gc` và `heap`.
- Không có wildcard thì matching thế nào? Chỉ tag set chính xác được chỉ định.
- `gc*` có nghĩa gì? Match các tag set chứa `gc`, kể cả khi có tag bổ sung.
- `gc+heap*` khác `gc+heap` thế nào? Bản có wildcard chấp nhận tag set có thêm tag khác.
- `all=info` làm gì? Chọn mọi tag combination ở ngưỡng info và các level nghiêm trọng hơn.
- Các level là gì? `off`, `error`, `warning`, `info`, `debug`, `trace`.
- `info` có nhận warning và error không? Có.
- `warning` có nhận info không? Không.
- Nếu bỏ level thì mặc định là gì? `info`.
- `off` có ý nghĩa gì? Không ghi message của selection đó.
- Kiểm tra tag có sẵn bằng cách nào? `java -Xlog:help` trên đúng runtime.
- Tag selection có điều khiển logger nghiệp vụ không? Không; nó điều khiển log nội bộ JVM.

Điểm cốt lõi: **`+` kết hợp tag, `,` tạo các selection độc lập, `*` mở rộng matching và level xác định ngưỡng chi tiết tích lũy.** Bắt đầu bằng selection exact và level vừa đủ, sau đó chỉ mở rộng khi câu hỏi chẩn đoán yêu cầu.