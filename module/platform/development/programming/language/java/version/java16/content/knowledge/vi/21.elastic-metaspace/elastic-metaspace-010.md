# Đọc jcmd VM.metaspace và VM.classloader_stats trên JVM đích

Khi điều tra metaspace tăng, cần biết bộ nhớ đang được dùng ở mức toàn JVM và class loader nào đang giữ metadata. HotSpot cung cấp hai lệnh chẩn đoán phù hợp: `jcmd <pid> VM.metaspace` cho biết trạng thái metaspace, còn `jcmd <pid> VM.classloader_stats` thống kê class loader, số class và các chunk/block được cấp phát.

Hai lệnh này bổ sung cho nhau. `VM.metaspace` giúp nhìn tổng thể, loại chunk và mức dùng theo loader; `VM.classloader_stats` giúp đối chiếu từng ClassLoaderData, số class và dung lượng chunk/block. Khi lấy nhiều snapshot ở cùng điều kiện tải, bạn có thể nhận ra xu hướng tăng bất thường sau mỗi lần deploy hoặc reload plugin.

Bài học tập trung vào cách chạy lệnh trên đúng JVM đích, đọc các trường quan trọng, so sánh kết quả theo thời gian và hiểu giới hạn của số liệu. Đây là các diagnostic command hiện hành của HotSpot trên JDK hiện đại; cú pháp chi tiết có thể thay đổi theo nhà cung cấp và phiên bản runtime.

## 1. Hai lệnh trả lời hai câu hỏi khác nhau

| Lệnh | Câu hỏi chính | Thông tin hữu ích |
|---|---|---|
| `jcmd <pid> VM.metaspace` | Metaspace của JVM đang ở trạng thái nào? | Reserved, committed, used, thống kê theo loader, chunk type, space type và virtual space |
| `jcmd <pid> VM.classloader_stats` | Class loader nào đang giữ class metadata và được cấp phát bao nhiêu? | ClassLoader, parent, CLD, số class, ChunkSz, BlockSz và loại loader |

`VM.metaspace` phù hợp để bắt đầu điều tra vì nó cho biết bức tranh tổng thể. `VM.classloader_stats` hữu ích khi cần xác định loader nào có số class hoặc lượng chunk tăng theo thời gian.

Hai lệnh là diagnostic command của HotSpot. Không giả định mọi JVM vendor hoặc mọi runtime đều cung cấp cùng tập lệnh. Hãy hỏi chính JVM đích bằng `jcmd <pid> help` trước khi dựa vào một tùy chọn cụ thể.

## 2. Điều kiện để attach vào JVM đích

`jcmd` gửi yêu cầu chẩn đoán tới một tiến trình Java đang chạy. Công cụ phải chạy trên cùng máy với JVM đích và thông thường cần cùng effective user và group đã dùng để khởi chạy JVM.

Trước khi chạy, kiểm tra:

- Có quyền truy cập tiến trình đích và thư mục tạm mà cơ chế attach sử dụng.
- Dùng JDK có công cụ `jcmd`; ưu tiên công cụ cùng JDK distribution/version với JVM đích.
- JVM đích là HotSpot và chưa tắt attach mechanism.
- Đang dùng đúng PID trong process namespace của JVM.
- Chính sách bảo mật và cấu hình container cho phép attach.

Một số ứng dụng chủ động khởi chạy với `-XX:+DisableAttachMechanism`. Khi đó các lệnh attach như `jcmd` có thể không kết nối được. Không thay đổi cấu hình production chỉ để chạy một lệnh chẩn đoán nếu chưa đánh giá tác động và quy trình restart.

### JVM chạy trong container

`jcmd -l` không liệt kê JVM chạy trong một Docker process riêng biệt. Nếu JVM nằm trong container, hãy tìm PID trong namespace phù hợp, thường bằng cách chạy `ps` và `jcmd` bên trong container hoặc dùng PID host đã xác minh đúng tiến trình.

PID trên host và PID bên trong container có thể khác nhau. Không chọn PID chỉ dựa trên tên ứng dụng hoặc một danh sách cũ.

## 3. Xác định đúng PID và phiên bản JVM

Liệt kê các JVM mà `jcmd` nhìn thấy:

~~~text
jcmd -l
~~~

Kết quả thường có PID, tên main class và một phần command line. Khi đã xác định được PID, kiểm tra phiên bản của tiến trình:

~~~text
jcmd <pid> VM.version
~~~

Hỏi JVM đích những diagnostic command đang hỗ trợ:

~~~text
jcmd <pid> help
~~~

Hỏi cú pháp của từng lệnh:

~~~text
jcmd <pid> help VM.metaspace
jcmd <pid> help VM.classloader_stats
~~~

Đây là bước quan trọng vì `jcmd` liệt kê các command mà JVM đích thực sự hỗ trợ. Không sao chép một option từ tài liệu của JDK khác nếu help trên JVM đang vận hành không có option đó.

Không dùng PID `0` trong thao tác điều tra thông thường. PID `0` gửi command tới tất cả JVM mà công cụ có thể tiếp cận, khiến phạm vi tác động rộng hơn mục tiêu.

## 4. Lấy snapshot metaspace tổng quan

Lệnh cơ bản:

~~~text
jcmd <pid> VM.metaspace
~~~

Lệnh này in thống kê metaspace của tiến trình. Trên JDK hiện đại, có thể dùng `scale` để chọn đơn vị:

~~~text
jcmd <pid> VM.metaspace scale=MB
~~~

Để lấy bản tóm tắt cơ bản:

~~~text
jcmd <pid> VM.metaspace basic=true scale=MB
~~~

`basic=true` yêu cầu bản tóm tắt cơ bản và không cần safepoint. Đây là lựa chọn thích hợp cho snapshot ban đầu hoặc khi muốn hạn chế ảnh hưởng của thao tác chẩn đoán. Tài liệu JDK 26 xếp `VM.metaspace` ở mức tác động trung bình, phụ thuộc số class đã nạp; bản basic giảm phần công việc cần thực hiện nhưng vẫn nên chạy có chủ đích.

Các giá trị scale hiện hành được tài liệu JDK 26 mô tả gồm `1`, `KB`, `MB`, `GB` và `dynamic`. Nếu không chỉ định, JVM chọn scale động.

## 5. Đọc các số liệu chính của VM.metaspace

Tên và bố cục chi tiết của phần output có thể khác theo phiên bản HotSpot, nhưng các khái niệm cần phân biệt gồm:

| Số liệu | Ý nghĩa | Cách đọc |
|---|---|---|
| Reserved | Vùng địa chỉ ảo JVM đã reserve cho metaspace | Không đồng nghĩa toàn bộ vùng này đang chiếm RAM vật lý |
| Committed | Phần vùng đã được commit để JVM sử dụng | Là lượng backing memory JVM đã yêu cầu cho vùng metaspace |
| Used | Phần metadata/block đang được sử dụng | Phản ánh nhu cầu metadata hiện tại rõ hơn reserved |
| Free hoặc waste | Phần chưa được dùng trong vùng đã commit hoặc phần lãng phí theo cách phân loại của output | Đọc theo nhãn cụ thể của phiên bản JVM |
| Class space | Phần liên quan đến compressed class space khi cấu hình tương ứng được bật | Không cộng hoặc so sánh với metaspace tổng mà bỏ qua cách JVM phân loại |

Không dùng `reserved` như số RAM ứng dụng đang chiếm. JVM có thể reserve vùng địa chỉ lớn nhưng chỉ commit một phần. Tương tự, `committed` có thể cao hơn `used` vì chunk còn chỗ trống được giữ để cấp phát tiếp.

Khi `used` giảm sau class unloading nhưng `committed` chưa giảm ngay, điều đó chưa đủ chứng minh memory leak. JVM có thể giữ chunk để tái sử dụng, và việc uncommit phụ thuộc trạng thái vùng nhớ cùng chính sách của allocator.

## 6. Xem metaspace theo class loader

Để xem phân bố mức dùng theo loader:

~~~text
jcmd <pid> VM.metaspace show-loaders=true scale=MB
~~~

Đây là bước hữu ích khi tổng `used` tăng và cần xác định nhóm loader đóng góp nhiều metadata. Output có thể bao gồm thông tin loader, số class và các số liệu sử dụng liên quan tùy phiên bản JDK.

Có thể yêu cầu phân rã theo loại chunk:

~~~text
jcmd <pid> VM.metaspace by-chunktype=true scale=MB
~~~

Hoặc phân rã theo loại không gian/loader:

~~~text
jcmd <pid> VM.metaspace by-spacetype=true scale=MB
~~~

Kết hợp các option nếu cần xem nhiều chiều trong cùng snapshot:

~~~text
jcmd <pid> VM.metaspace show-loaders=true by-chunktype=true by-spacetype=true scale=MB
~~~

Để xem sâu hơn vùng địa chỉ ảo và danh sách chunk rảnh:

~~~text
jcmd <pid> VM.metaspace vslist=true scale=MB
jcmd <pid> VM.metaspace chunkfreelist=true scale=MB
~~~

`vslist` và `chunkfreelist` phù hợp khi đã có giả thuyết về vùng virtual space hoặc chunk manager. Không cần bật tất cả option trong lần kiểm tra đầu tiên.

### Khi nào dùng show-classes?

Có thể liệt kê class theo từng loader:

~~~text
jcmd <pid> VM.metaspace show-loaders=true show-classes=true scale=MB
~~~

Đầu ra có thể rất lớn nếu ứng dụng nạp nhiều class. Tài liệu JDK 26 xếp `VM.metaspace` ở mức tác động trung bình theo số class đã nạp; chỉ bật `show-classes` khi cần khoanh vùng cụ thể, lưu output có kiểm soát và tránh chạy lặp liên tục trong giờ tải cao.

## 7. Đọc thống kê từng loader bằng VM.classloader_stats

Lệnh:

~~~text
jcmd <pid> VM.classloader_stats
~~~

Lệnh này in thống kê về các class loader trong JVM. Trong HotSpot, output thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| ClassLoader | Địa chỉ object ClassLoader; bootstrap loader có thể không có object Java tương ứng |
| Parent | Địa chỉ class loader cha |
| CLD* | Địa chỉ cấu trúc nội bộ ClassLoaderData của HotSpot |
| Classes | Số class được ghi nhận cho entry |
| ChunkSz | Tổng kích thước các metaspace chunk đã cấp phát |
| BlockSz | Tổng kích thước các block đã cấp phát bên trong chunk |
| Type | Tên lớp triển khai class loader |

Ví dụ minh họa rút gọn:

~~~text
ClassLoader          Parent              CLD*                Classes   ChunkSz   BlockSz  Type
0x...                0x...                0x...                     120     65536     48200  jdk.internal.loader.ClassLoaders$AppClassLoader
0x...                0x...                0x...                      48     32768     19400  com.example.PluginClassLoader
0x...                0x...                0x...                      36     32768     15200  com.example.PluginClassLoader
Total = 3                                                           204    131072     82800
~~~

Các địa chỉ và số liệu trên chỉ là ví dụ để giải thích cách đọc, không phải output chuẩn cho mọi ứng dụng. Tên cột, cách nhóm và chi tiết hidden class có thể khác theo phiên bản HotSpot.

`ChunkSz` là tổng dung lượng chunk metaspace được cấp cho entry; `BlockSz` là tổng dung lượng block đã cấp trong các chunk đó. Hai giá trị này không phải kích thước heap của class loader và cũng không phải tổng bytecode của các class.

Trong output HotSpot, các giá trị `ChunkSz` và `BlockSz` thường được in dưới dạng byte. `VM.classloader_stats` không có tùy chọn `scale` như `VM.metaspace`, vì vậy cần quy đổi khi so sánh với số liệu MB/GB ở snapshot tổng quan. Đây là thống kê dung lượng đã cấp, không phải phép đo chính xác riêng phần metadata còn sống.

Một số output có thể hiển thị thêm dòng cho hidden classes. Hãy đọc phần tổng kết của chính output để hiểu cách JVM cộng các dòng này vào tổng số class và dung lượng.

### Địa chỉ ClassLoader và CLD không phải định danh ổn định

Các giá trị dạng `0x...` là địa chỉ nội bộ của tiến trình hiện tại. Chúng có thể thay đổi sau restart và không nên được lưu như ID lâu dài trong dashboard hoặc hệ thống nghiệp vụ.

Không suy ra tên plugin chỉ từ địa chỉ. Cột `Type` cho biết lớp triển khai loader; nhiều plugin có thể dùng cùng một loại class loader. Để xác định loader thuộc plugin hoặc deployment nào, hãy đối chiếu thời điểm deploy, log ứng dụng, tên module và thông tin mà ứng dụng ghi nhận khi tạo loader.

## 8. Kết hợp hai lệnh để khoanh vùng

Một quy trình cơ bản:

1. Chạy `VM.metaspace basic=true scale=MB` để ghi nhận tổng reserved, committed và used.
2. Chạy `VM.metaspace show-loaders=true scale=MB` để xem phân bố theo loader.
3. Chạy `VM.classloader_stats` để đối chiếu số class và chunk/block của từng loader.
4. Ghi timestamp, PID, phiên bản JVM và trạng thái workload cùng output.
5. Lặp lại sau một chu kỳ workload hoặc deploy tương tự.

Ví dụ chuỗi lệnh:

~~~text
jcmd <pid> VM.version
jcmd <pid> VM.metaspace basic=true scale=MB
jcmd <pid> VM.metaspace show-loaders=true scale=MB
jcmd <pid> VM.classloader_stats
~~~

Nếu kết quả cho thấy một loader có số class hoặc `BlockSz` tăng nhanh, lấy snapshot tiếp theo sau khi workload tương đương. Không kết luận từ một dòng đơn lẻ hoặc một thời điểm startup.

## 9. So sánh snapshot trước và sau deploy/reload

Để phát hiện class loader leak, hãy so sánh các snapshot ở những thời điểm tương đương:

| Thời điểm | Việc thực hiện | Điều cần ghi nhận |
|---|---|---|
| T0 | Sau startup và khi ứng dụng ổn định | Mốc nền về loader, class, used và committed |
| T1 | Sau khi nạp plugin hoặc triển khai module | Loader/class mới được tạo và lượng metaspace tăng |
| T2 | Sau khi unload plugin hoặc undeploy ứng dụng | Loader nào biến mất, số class nào giảm |
| T3 | Sau khi GC/class unloading có cơ hội diễn ra và workload lắng xuống | Used, committed và thống kê loader còn lại |
| T4 | Sau chu kỳ deploy/reload tiếp theo | Xu hướng có lặp lại và tích lũy hay không |

Không yêu cầu committed memory phải quay về đúng giá trị T0. Elastic Metaspace có thể giữ chunk đã rảnh để tái sử dụng. Quan trọng hơn là xem class loader cũ có còn được ghi nhận hay không, số class và block được cấp phát có tiếp tục tăng qua các chu kỳ hay không, và `used` có xu hướng ổn định sau khi workload kết thúc hay không.

Không nên chạy `GC.run` trước mọi snapshot chỉ để ép số liệu giảm. Lệnh đó yêu cầu GC chạy và có thể làm thay đổi hành vi/timing của ứng dụng. Hãy quan sát theo chu kỳ GC tự nhiên trước; chỉ thực hiện thử nghiệm ép GC trong môi trường kiểm thử có kiểm soát.

## 10. Diễn giải các mẫu kết quả thường gặp

| Kết quả quan sát | Cách diễn giải ban đầu | Bước tiếp theo |
|---|---|---|
| Used tăng cùng số class tăng | Ứng dụng có thể đang nạp thêm class hợp lệ | Xác định tính năng, module hoặc plugin vừa được nạp |
| Sau mỗi redeploy, loader count tăng và loader cũ vẫn còn | Nghi ngờ loader cũ đang bị giữ tham chiếu | Kiểm tra thread, ThreadLocal, context class loader, cache và registry |
| Classes/BlockSz giảm nhưng Committed không giảm tương ứng | Chunk rảnh có thể được giữ để tái sử dụng | Theo dõi thêm snapshot; đối chiếu chunk free list và committed |
| Reserved lớn nhưng Committed thấp | JVM giữ address space nhưng chưa commit toàn bộ | Không kết luận RAM vật lý đang bị chiếm tương ứng |
| Một loader có ChunkSz lớn nhưng Classes ít | Loader có thể đang giữ chunk với nhiều phần chưa dùng | Theo dõi sau khi loader kết thúc; không coi một snapshot là leak |
| Tổng metaspace tăng nhưng loader statistics ít thay đổi | Có thể cần xem thêm class space, hidden classes hoặc các chiều phân rã khác | Dùng `VM.metaspace` với by-chunktype/by-spacetype và kiểm tra runtime cụ thể |

Các mẫu này là gợi ý điều tra, không phải quy tắc kết luận tự động. Mức dùng phụ thuộc framework, số class, kiểu class loader, hidden class và cách ứng dụng tạo proxy hoặc bytecode động.

## 11. Phân biệt class loader leak với tăng trưởng hợp lệ

Class loader leak thường biểu hiện qua việc loader cũ tiếp tục tồn tại sau khi module/plugin đã được unload. Các dấu hiệu cần kết hợp:

- Số loader hoặc số class tăng qua các chu kỳ deploy tương tự.
- Loader của deployment cũ vẫn xuất hiện trong `VM.classloader_stats`.
- Số block/chunk được cấp phát tiếp tục tích lũy.
- Mức used không trở về vùng ổn định sau khi workload lắng xuống.
- Ứng dụng có thread, ThreadLocal, callback, cache hoặc context class loader giữ tham chiếu tới loader cũ.

Ngược lại, tăng metaspace trong lúc startup, tải plugin mới hoặc warm up framework có thể là bình thường. Nếu loader count và class count ổn định sau giai đoạn khởi tạo, đó chưa phải dấu hiệu leak.

Hai lệnh chẩn đoán chỉ cho biết thống kê, không cho biết đường tham chiếu nào đang giữ một loader sống. Nếu nghi ngờ leak, cần bước điều tra tiếp theo bằng heap dump và công cụ phân tích đường dẫn tới GC root, hoặc instrument lifecycle của class loader trong ứng dụng.

## 12. Phân biệt VM.classloader_stats với VM.classloaders

JDK hiện đại còn có command `VM.classloaders`, nhưng đây là lệnh khác:

~~~text
jcmd <pid> VM.classloaders
~~~

`VM.classloader_stats` tập trung vào thống kê class loader. `VM.classloaders` in cây phân cấp loader và có thể nhận các option như `show-classes`, `verbose` và `fold` trên các phiên bản hỗ trợ.

Khi câu hỏi là loader nào có nhiều class hoặc cấp phát nhiều chunk/block, bắt đầu bằng `VM.classloader_stats`. Khi cần xem quan hệ cha/con hoặc chi tiết loader hierarchy, kiểm tra `help VM.classloaders` trên JVM đích rồi dùng command riêng đó.

Không nhầm `VM.classloaders` với `VM.classloader_stats`, và không giả định hai lệnh có cùng option.

## 13. Xử lý lỗi khi jcmd không attach được

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy PID | JVM nằm trong container hoặc namespace khác | Dùng `ps` trong đúng namespace; xác minh PID host/container |
| Attach bị từ chối | Khác user/group hoặc quyền truy cập hạn chế | Chạy công cụ với cùng tài khoản hiệu lực đã khởi chạy JVM |
| Không có phản hồi | JVM bận, attach mechanism bị tắt hoặc tiến trình không phản hồi | Kiểm tra trạng thái process và cấu hình khởi động |
| Không có command VM.metaspace | JVM không phải HotSpot hoặc phiên bản/vendor không hỗ trợ | Chạy `jcmd <pid> help` trên target |
| Option không hợp lệ | Cú pháp khác giữa các JDK hoặc gõ sai | Chạy `jcmd <pid> help VM.metaspace` |
| Output không giống ví dụ | Khác phiên bản, vendor hoặc cấu hình VM | Dựa vào help và nhãn output thực tế của target |

`jcmd` là công cụ attach cục bộ, không phải giao thức chẩn đoán từ xa. Khi cần quản lý JVM ở máy khác, hãy dùng giải pháp giám sát/management được tổ chức cấu hình rõ ràng thay vì giả định có thể chạy `jcmd` trực tiếp qua mạng.

## 14. Mức tác động và cách chạy an toàn

Tài liệu Oracle JDK 26 mô tả:

- `VM.classloader_stats`: Impact Low.
- `VM.metaspace`: Impact Medium, phụ thuộc số class đã nạp.
- `VM.metaspace basic=true`: bản tóm tắt cơ bản không cần safepoint.

Thực hành phù hợp:

1. Bắt đầu với `VM.metaspace basic=true`.
2. Chạy `VM.classloader_stats` để có thống kê loader.
3. Chỉ bật `show-loaders`, `by-chunktype`, `by-spacetype` khi cần thêm chiều phân tích.
4. Chỉ bật `show-classes` cho một lần điều tra có mục tiêu vì output có thể lớn.
5. Lưu output có timestamp và giới hạn quyền truy cập vì tên class, loại loader và địa chỉ nội bộ có thể tiết lộ cấu trúc ứng dụng.
6. Tránh chạy lặp dày đặc hoặc thu thập quá nhiều output trong giờ cao điểm.

Không dùng các con số trong output làm API ổn định để ứng dụng tự điều chỉnh. Đây là số liệu chẩn đoán của HotSpot, hữu ích cho vận hành và điều tra.

## 15. Runbook điều tra metaspace tăng

Khi nhận cảnh báo metaspace tăng, có thể thực hiện theo thứ tự:

1. Xác minh JVM đích, PID, phiên bản và tài khoản attach.
2. Ghi snapshot `VM.metaspace basic=true scale=MB`.
3. Ghi `VM.classloader_stats`.
4. Nếu cần, lấy `VM.metaspace show-loaders=true scale=MB`.
5. Đối chiếu thời điểm tăng với deploy, plugin load, proxy generation và hoạt động framework.
6. Chờ workload ổn định và class unloading có cơ hội diễn ra; lấy snapshot tiếp theo.
7. So sánh loader, class count, ChunkSz, BlockSz, used và committed.
8. Nếu loader cũ tồn tại qua nhiều chu kỳ, tìm strong reference bằng heap dump hoặc công cụ phân tích.
9. Sau khi xác định nguyên nhân, sửa lifecycle hoặc cache; chỉ điều chỉnh giới hạn metaspace nếu dữ liệu cho thấy workload hợp lệ cần thêm native memory.

Runbook này giúp thu thập dữ liệu có thể so sánh và tránh phản ứng chỉ dựa trên một số tổng dung lượng.

## 16. Checklist review

- [ ] Đã xác minh đúng JVM đích và PID trong đúng namespace.
- [ ] Đã kiểm tra phiên bản JVM và các command bằng `jcmd <pid> help`.
- [ ] Đã attach bằng effective user/group phù hợp.
- [ ] Đã lấy snapshot cơ bản bằng `VM.metaspace basic=true`.
- [ ] Đã đọc `VM.classloader_stats` và hiểu ClassLoader, Parent, CLD*, Classes, ChunkSz, BlockSz, Type.
- [ ] Đã phân biệt reserved, committed và used.
- [ ] Đã xem thống kê theo loader trước khi bật `show-classes`.
- [ ] Đã ghi timestamp, PID, phiên bản và trạng thái workload cho mỗi snapshot.
- [ ] Đã so sánh nhiều chu kỳ deploy/reload ở điều kiện tương đương.
- [ ] Không kết luận leak chỉ từ committed memory chưa giảm.
- [ ] Không nhầm địa chỉ pointer với định danh loader ổn định.
- [ ] Không dùng `VM.classloaders` thay cho `VM.classloader_stats` khi cần thống kê chunk/block.
- [ ] Đã bảo vệ output vì nó có thể chứa tên class và thông tin nội bộ.

## 17. Ghi nhớ

- `jcmd <pid> VM.metaspace` cho biết trạng thái metaspace; `VM.classloader_stats` phân rã thống kê theo class loader.
- Dùng `jcmd -l` để tìm PID trong namespace nhìn thấy được; container có thể cần tìm PID bên trong bằng `ps`.
- `jcmd` cần chạy trên cùng máy và thường cần cùng effective user/group với JVM đích.
- `VM.metaspace basic=true` là snapshot cơ bản không cần safepoint.
- `show-loaders`, `by-chunktype`, `by-spacetype`, `vslist` và `chunkfreelist` giúp xem sâu hơn khi cần.
- `show-classes` có thể tạo output lớn; chỉ bật khi có mục tiêu rõ ràng.
- `VM.classloader_stats` cho biết số class và dung lượng chunk/block theo entry; ChunkSz và BlockSz không phải heap size.
- Reserved, committed và used là ba số liệu khác nhau.
- Pointer ClassLoader/CLD là địa chỉ nội bộ của tiến trình, không phải ID lâu dài.
- Một snapshot không đủ kết luận class loader leak; hãy so sánh nhiều chu kỳ workload/deploy.
- Lệnh thống kê không chỉ ra đường tham chiếu giữ loader; heap dump hoặc phân tích GC root có thể cần ở bước tiếp theo.

Khi kết hợp `VM.metaspace` và `VM.classloader_stats`, bạn có thể đi từ dấu hiệu tổng thể tới loader cụ thể đang đóng góp vào mức dùng metadata. Hãy chọn đúng JVM, dùng mức chi tiết phù hợp, ghi lại snapshot theo thời gian và kết hợp với lifecycle deploy/unload để phân biệt tăng trưởng hợp lệ với class loader leak.

## Tài liệu tham khảo

- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — cú pháp jcmd, điều kiện attach, danh sách command, option và mức tác động của VM.metaspace/VM.classloader_stats.
- [Java SE 26 Troubleshooting Guide — Class Loader Statistics](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — sử dụng jcmd để thu thập class loader statistics khi điều tra metaspace.
- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387) — bối cảnh quản lý metaspace được giới thiệu trong Java 16.
