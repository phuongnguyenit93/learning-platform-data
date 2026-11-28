# Tổ chức cấp phát metaspace và giảm phân mảnh ở mức khái niệm

Metaspace là vùng native memory của HotSpot JVM dùng để lưu metadata của các class đã được nạp. Khi ứng dụng tạo nhiều class, nạp class động hoặc sử dụng nhiều class loader, nhu cầu metaspace có thể tăng theo thời gian. Java 16 đưa vào Elastic Metaspace theo JEP 387, viết lại cơ chế quản lý vùng nhớ này để sử dụng bộ nhớ linh hoạt hơn, giảm lãng phí và trả lại các vùng không còn cần thiết cho hệ điều hành sau khi class loader được giải phóng.

Muốn hiểu Elastic Metaspace, cần tách ba vấn đề: class loader sở hữu metadata trong suốt vòng đời của nó; các chunk là đơn vị trung gian để cấp phát nhanh; và commit/uncommit quyết định phần vùng nhớ native nào đang được backing bởi bộ nhớ thực. Cơ chế buddy allocator giúp chia và ghép chunk, trong khi commit granule cho phép JVM thu hồi phần backing memory không còn sử dụng.

Bài học này giải thích mô hình ở mức khái niệm, cách nó giảm phân mảnh, các giới hạn vẫn còn tồn tại và cách quan sát metaspace bằng công cụ JDK hiện hành. Trọng tâm là hành vi từ Java 16 vẫn được dùng trên các JDK mới, không dựa vào mô hình allocator cũ đã được thay thế.

## 1. Metaspace lưu gì và nằm ở đâu?

Metaspace lưu metadata mà JVM cần để hiểu và thực thi class đã nạp, ví dụ thông tin cấu trúc class, method, constant pool và các cấu trúc nội bộ liên quan. Metadata này được quản lý trong native memory, nằm ngoài Java heap.

| Vùng nhớ | Nội dung điển hình | Được quản lý bởi |
|---|---|---|
| Java heap | Object của ứng dụng, bao gồm object đại diện cho java.lang.Class | Garbage Collector |
| Metaspace | Metadata nội bộ của class đã nạp | Cơ chế quản lý native memory của HotSpot |
| Compressed Class Space | Vùng riêng trong metaspace dành cho compressed class pointers khi cấu hình HotSpot bật chế độ tương ứng | JVM |
| Native memory khác | Thread stack, code cache, buffer native và cấu trúc runtime khác | JVM, thư viện native hoặc hệ điều hành |

Không nên đồng nhất object java.lang.Class với toàn bộ metadata của class. Object Class mà code Java nhìn thấy nằm trên heap; các cấu trúc metadata nội bộ của VM được lưu trong metaspace.

Metaspace tăng không nhất thiết có nghĩa Java heap đang thiếu bộ nhớ. Một ứng dụng có thể có heap còn nhiều chỗ nhưng vẫn gặp OutOfMemoryError: Metaspace nếu không còn đủ native memory cho class metadata hoặc đã chạm giới hạn metaspace được cấu hình.

## 2. Vì sao class loader quyết định vòng đời metadata?

Mỗi class được định nghĩa bởi một class loader cụ thể. Hai class có cùng tên đầy đủ nhưng được định nghĩa bởi hai class loader khác nhau vẫn là hai kiểu khác nhau trong JVM.

Vì vậy, metadata gắn với vòng đời của class loader đã định nghĩa class. Khi class loader không còn reachable và JVM thực hiện class unloading, metadata thuộc loader đó có thể được giải phóng theo nhóm.

Ví dụ các tình huống thường tạo class loader:

- Ứng dụng server triển khai và gỡ triển khai nhiều web application.
- Plugin system nạp và thay thế plugin trong lúc JVM vẫn chạy.
- Framework tạo class động cho proxy, reflection hoặc bytecode generation.
- Test runner hoặc công cụ phát triển tạo class loader riêng cho từng lần chạy.

Nếu ứng dụng tạo class loader mới liên tục nhưng vẫn giữ tham chiếu tới loader cũ, metadata của các class do loader cũ định nghĩa không thể được giải phóng. Đây thường là vấn đề quản lý vòng đời class loader, không phải thứ mà allocator có thể tự sửa.

### close() không đồng nghĩa class unloading

Một số class loader như URLClassLoader có phương thức close() để đóng các tài nguyên như JAR file handle. Gọi close() không tự làm class loader trở nên unreachable và không bảo đảm class được unload.

Để metadata có thể được thu hồi, ứng dụng cần:

1. Ngừng sử dụng class loader và các class do nó định nghĩa.
2. Đóng tài nguyên của loader nếu loại loader hỗ trợ close().
3. Xóa các strong reference tới loader, Class, instance, Method, MethodHandle và object liên quan.
4. Kiểm tra thread, ThreadLocal, context class loader, registry, callback và cache không còn giữ loader.
5. Để GC có cơ hội thực hiện class unloading.

GC quyết định thời điểm thu hồi; ứng dụng không thể yêu cầu JVM unload một class cụ thể theo cách xác định tức thời.

## 3. Từ yêu cầu metadata tới một arena

Để cấp phát nhanh, HotSpot tổ chức vùng metaspace theo class loader. Có thể hình dung mỗi loader sở hữu một arena: khi JVM cần thêm metadata cho loader đó, arena cấp phát từ phần chunk đang có. Khi chunk gần hết, arena yêu cầu thêm chunk từ bộ quản lý chunk dùng chung.

~~~text
Class Loader A
    |
    v
Metaspace Arena A ---- chunk ----+
                    ---- chunk   |
                                  |
Class Loader B                    v
    |                       Chunk Manager
    v                            |
Metaspace Arena B ---- chunk ----+
                                 |
                                 v
                         Virtual memory
                         commit granules
~~~

Arena giúp thao tác cấp phát nhỏ diễn ra nhanh: thay vì yêu cầu hệ điều hành cấp phát từng cấu trúc metadata, JVM thường lấy một vùng lớn hơn rồi chia nhỏ nội bộ cho các lần cấp phát tiếp theo.

Đổi lại, một phần cuối chunk có thể chưa được dùng hết. Đây là một dạng lãng phí nội bộ ở mức arena: phần trống vẫn nằm trong chunk thuộc quyền sử dụng của loader và không thể tùy tiện chuyển cho loader khác. Elastic Metaspace có thể trì hoãn commit phần chưa dùng, nhờ đó giảm lượng backing memory dù chunk vẫn được giữ.

## 4. Chunk là đơn vị trung gian, không phải một class

Chunk là vùng nhớ được Metaspace cấp cho arena của class loader. Kích thước chunk có nhiều cấp để phù hợp với nhu cầu tăng trưởng khác nhau. Arena phân bổ metadata từ chunk bằng cách tiến con trỏ cấp phát; khi không đủ chỗ, nó lấy chunk tiếp theo.

Một cách hình dung:

~~~text
Chunk được cấp cho Loader A
+---------------------------------------+
| metadata đã dùng | phần chưa dùng     |
+---------------------------------------+
^                  ^
đầu chunk          con trỏ cấp phát
~~~

Phần chưa dùng ở cuối chunk không nhất thiết là memory leak. Có thể loader vẫn sẽ cần nó khi nạp thêm class. Tuy nhiên, nếu loader sống rất lâu nhưng chỉ dùng một phần nhỏ của chunk, phần trống vẫn chiếm dung lượng chunk và tạo phân mảnh nội bộ; cơ chế commit theo nhu cầu giúp tránh phải backing toàn bộ phần trống đó bằng memory.

Elastic Metaspace cải thiện cách quản lý phần này bằng cách commit backing memory theo nhu cầu và có thể uncommit các vùng không còn cần thiết, thay vì buộc toàn bộ chunk phải được commit ngay khi cấp phát.

## 5. Buddy allocator chia và ghép chunk như thế nào?

JEP 387 dùng buddy-style allocator để quản lý chunk. Các chunk được tổ chức theo các kích thước dạng lũy thừa của hai. Khi cần chunk nhỏ hơn một chunk đang rảnh, bộ quản lý có thể chia chunk lớn thành hai nửa cùng cấp, rồi tiếp tục chia cho đến khi có kích thước phù hợp.

Ví dụ khái niệm:

~~~text
Một chunk lớn đang rảnh
          [       8 units       ]
                    |
                  split
             +------+------+
             |             |
         [4 units]     [4 units]
             |
           split
         +---+---+
         |       |
      [2 units] [2 units]
~~~

Khi một arena giải phóng chunk, Chunk Manager đưa chunk về danh sách rảnh. Nếu chunk buddy liền kề cũng rảnh và đủ điều kiện ghép, allocator có thể gộp hai chunk thành một chunk lớn hơn. Quá trình ghép có thể tiếp tục nhiều cấp.

Điều này giúp giảm phân mảnh ngoại vi ở tầng chunk: thay vì giữ nhiều mảnh nhỏ không thể đáp ứng yêu cầu lớn, allocator có thể tái hợp các buddy liền kề để tạo vùng lớn hơn.

Các kích thước trong sơ đồ chỉ là ví dụ tương đối. Không nên viết ứng dụng dựa trên một kích thước chunk nội bộ cụ thể vì đó là chi tiết triển khai của HotSpot, không phải hợp đồng API Java.

## 6. Commit và uncommit: khác với reserve

Để hiểu tính đàn hồi của metaspace, cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Reserve address space | JVM giữ một vùng địa chỉ ảo để có thể sử dụng về sau |
| Commit memory | JVM yêu cầu hệ điều hành backing một phần vùng địa chỉ đó để sử dụng |
| Uncommit memory | JVM trả backing memory của vùng không còn cần; vùng địa chỉ có thể vẫn được giữ để tái sử dụng |

Một vùng đã reserve không đồng nghĩa toàn bộ vùng đó đang tiêu thụ RAM vật lý. Tương tự, một chunk có thể được giao cho arena nhưng chỉ phần cần thiết mới được commit.

Elastic Metaspace chia backing memory thành các commit granule. Đây là đơn vị tối thiểu mà cơ chế quản lý dùng để commit hoặc uncommit. Granule nhỏ hơn giúp thu hồi vùng rảnh linh hoạt hơn, nhưng kích thước granule là chi tiết triển khai và phụ thuộc JVM/platform.

~~~text
Một vùng metaspace đã reserve
+---------+---------+---------+---------+
| committed | committed | uncommitted | free |
+---------+---------+---------+---------+
              |
              +-- chỉ các granule cần dùng được commit
~~~

Khi class loader còn hoạt động, phần metadata đang dùng phải được giữ. Khi loader chết và arena trả chunk về Chunk Manager, các vùng backing không còn cần thiết có thể được uncommit. JVM vẫn có thể giữ vùng địa chỉ ảo để cấp phát lại sau này.

Do đó, nhìn thấy reserved memory cao không đồng nghĩa ứng dụng đang giữ lượng RAM vật lý tương ứng. Khi đánh giá memory footprint, cần xem committed memory và số liệu hệ điều hành, không chỉ nhìn tổng vùng địa chỉ đã reserve.

## 7. Elastic Metaspace cải thiện điều gì từ Java 16?

JEP 387 thay thế phần triển khai metaspace cũ bằng một thiết kế mới. Các mục tiêu chính là giảm footprint, cải thiện khả năng trả lại bộ nhớ không dùng cho hệ điều hành sau class unloading và làm allocator dễ duy trì hơn.

| Khía cạnh | Mô hình trước Java 16 | Elastic Metaspace từ Java 16 |
|---|---|---|
| Quản lý chunk | Cơ chế cũ với khả năng tái sử dụng và thu hồi kém linh hoạt hơn | Buddy-style allocator chia/ghép chunk |
| Commit | Chunk thường phải commit thô hơn khi được cấp | Có thể commit theo nhu cầu và granule |
| Uncommit | Khả năng trả lại backing memory hạn chế hơn | Có thể uncommit vùng rảnh với granularity nhỏ hơn |
| Class loader unload | Trả metadata của loader về metaspace | Trả chunk về manager, ghép buddy và có thể uncommit backing memory |
| Mục tiêu | Tăng hiệu quả cấp phát | Giảm footprint và tăng tính đàn hồi của native memory |

Điểm quan trọng là Elastic Metaspace không thay đổi ý nghĩa của metaspace và không làm metadata của class loader đang sống tự biến mất. Nó cải thiện cách quản lý các vùng nhớ đã trở nên rảnh.

## 8. Phân mảnh nội bộ và phân mảnh ngoại vi

Hai dạng phân mảnh thường được dùng để giải thích lãng phí bộ nhớ:

**Phân mảnh nội bộ (internal fragmentation)** là phần không dùng nằm bên trong vùng đã cấp cho một owner. Ví dụ arena của loader được giao chunk nhưng chỉ sử dụng một phần. Phần còn lại không thể ngay lập tức dùng cho loader khác khi chunk vẫn thuộc arena.

**Phân mảnh ngoại vi (external fragmentation)** là tình huống có nhiều vùng rảnh nhưng chúng nằm rời rạc hoặc sai kích thước, khiến một yêu cầu lớn không được đáp ứng dù tổng dung lượng rảnh có thể đủ.

~~~text
Internal fragmentation:
+-------------------------------+
| used | unused tail in chunk   |
+-------------------------------+
        chunk vẫn thuộc arena

External fragmentation:
+------+-----+------+-----+------+
| used |free | used |free | used |
+------+-----+------+-----+------+
   các vùng free nằm rời rạc
~~~

Buddy allocator giúp giảm phân mảnh ngoại vi bằng cách ghép các buddy liền kề khi cả hai đã rảnh. Commit granule giúp uncommit backing memory của phần không còn dùng. Hai cơ chế giải quyết hai lớp vấn đề khác nhau.

Elastic Metaspace giảm lãng phí nhưng không thể loại bỏ hoàn toàn phân mảnh. Metadata còn được một class loader đang sống sử dụng vẫn cần được giữ; chunk chưa thể trả về manager cho tới khi arena giải phóng nó.

## 9. Vì sao class unloading quan trọng với plugin và ứng dụng server?

Hãy xem một server hỗ trợ reload plugin:

1. Plugin A được nạp bằng PluginClassLoader A.
2. Các class của plugin được định nghĩa và metadata được cấp phát trong metaspace.
3. Plugin A bị gỡ khỏi hệ thống.
4. Nếu thread, cache hoặc registry vẫn giữ PluginClassLoader A, loader chưa thể được thu gom.
5. Khi mọi tham chiếu mạnh được loại bỏ và GC thực hiện class unloading, arena của loader mới có thể được giải phóng.
6. Chunk được trả lại cho Metaspace và backing memory không còn cần có thể được uncommit.

Đây là lý do số class loader và khả năng unload có ý nghĩa khi điều tra metaspace tăng liên tục. Một ứng dụng có thể nạp và unload hàng nghìn class loader trong suốt vòng đời mà không nhất thiết bị leak, miễn là loader cũ thực sự trở nên unreachable và quá trình unloading diễn ra.

Ngược lại, nếu mỗi lần reload tạo một loader mới nhưng cache toàn cục giữ một Class hoặc Method từ loader cũ, metadata cũ vẫn tồn tại. Tăng MaxMetaspaceSize chỉ trì hoãn lỗi chứ không giải quyết nguyên nhân giữ tham chiếu.

## 10. Các nguyên nhân phổ biến khiến metaspace tăng

| Nguyên nhân | Biểu hiện | Hướng kiểm tra |
|---|---|---|
| Nạp class động liên tục | Số class hoặc class loader tăng | Kiểm tra class loading và thống kê theo loader |
| Class loader leak | Loader cũ không được unload sau redeploy | Tìm strong reference, thread và cache giữ loader |
| Proxy/bytecode generation không được kiểm soát | Số class sinh động tăng cao | Kiểm tra framework, proxy cache và lifecycle |
| Tạo nhiều class loader cho tác vụ ngắn | Loader count tăng nhanh | Xem có thể tái sử dụng loader hay không |
| Cấu hình classpath/module/provider thay đổi | Tập class được nạp lớn hơn | So sánh module và dependency giữa các lần chạy |
| Giới hạn metaspace quá thấp | OOME khi nạp thêm class | Xác minh giới hạn và mức dùng thực tế |

Metaspace tăng trong giai đoạn startup hoặc sau khi triển khai module mới có thể là bình thường. Điều cần chú ý là xu hướng tăng liên tục sau các chu kỳ workload/redeploy tương tự, đặc biệt khi số class loader không giảm hoặc committed memory không được thu hồi như mong đợi.

## 11. Đọc OutOfMemoryError đúng ngữ cảnh

Một số thông báo lỗi thường gặp:

| Thông báo | Ý nghĩa cần xem xét |
|---|---|
| OutOfMemoryError: Metaspace | JVM không thể cấp thêm native memory cho class metadata hoặc đã đạt MaxMetaspaceSize |
| OutOfMemoryError: Compressed class space | Vùng compressed class space đã đạt giới hạn hoặc không thể cấp thêm vùng cần thiết |
| Java heap space | Không đủ Java heap cho object allocation; đây là vấn đề khác với metaspace |
| unable to create native thread | Native memory hoặc giới hạn hệ điều hành không đủ để tạo thread; không mặc định là metaspace |

Không nên tăng heap khi lỗi chỉ ra metaspace. Cũng không nên tăng MaxMetaspaceSize ngay mà chưa xác định ứng dụng có thực sự cần nhiều metadata hơn hay class loader đang bị giữ lại.

MaxMetaspaceSize là tùy chọn JVM hiện hành để giới hạn lượng native memory dành cho class metadata. Nếu đặt giới hạn, hãy cân nhắc workload, số class, số loader và headroom cho các đợt deploy/reload. Mặc định JVM không đặt một giới hạn metaspace nhỏ cố định cho mọi ứng dụng; mức dùng phụ thuộc ứng dụng và tài nguyên hệ thống.

## 12. Quan sát metaspace bằng jcmd trên JDK hiện đại

JDK cung cấp lệnh VM.metaspace để in thống kê metaspace của một tiến trình HotSpot đang chạy. Trước tiên liệt kê JVM:

~~~text
jcmd -l
~~~

In thống kê cơ bản:

~~~text
jcmd <pid> VM.metaspace basic=true scale=MB
~~~

Xem mức sử dụng theo class loader:

~~~text
jcmd <pid> VM.metaspace show-loaders=true scale=MB
~~~

Xem thêm class được nạp bởi từng loader:

~~~text
jcmd <pid> VM.metaspace show-loaders=true show-classes=true scale=MB
~~~

Thống kê theo loader giúp tìm loader bất thường, nhưng tùy chọn show-classes có thể tạo đầu ra lớn khi ứng dụng nạp nhiều class. Lệnh VM.metaspace có mức tác động trung bình tùy theo số class đã nạp; chỉ yêu cầu mức chi tiết cần thiết. Tên tùy chọn và mức chi tiết phụ thuộc phiên bản JDK. Hãy dùng jcmd đi cùng JDK đang chạy tiến trình và xem trợ giúp của lệnh trên đúng runtime đó:

~~~text
jcmd <pid> help VM.metaspace
~~~

Khi so sánh trước/sau redeploy, nên chụp thống kê ở các thời điểm tương đương: sau startup ổn định, sau khi tải plugin, sau khi unload/redeploy và sau khi workload đã lắng xuống. Một lần snapshot đơn lẻ thường không đủ để kết luận leak.

## 13. Native Memory Tracking giúp phân biệt reserved và committed

Native Memory Tracking (NMT) có thể theo dõi native memory do HotSpot quản lý. Cần bật khi JVM khởi động:

~~~text
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó lấy summary:

~~~text
jcmd <pid> VM.native_memory summary
~~~

Có thể đặt baseline và xem chênh lệch:

~~~text
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

NMT phân loại native memory theo subsystem, trong đó có Class. Nó giúp xem xu hướng reserved/committed và thay đổi giữa các thời điểm. NMT có overhead và chỉ theo dõi các phần native memory do HotSpot quản lý; nó không phải công cụ thống kê toàn bộ allocation của thư viện native bên thứ ba.

Không bật NMT một cách tùy tiện trong mọi production workload. Có thể bật ở môi trường staging hoặc trong một đợt điều tra có mục tiêu, đánh giá overhead và tuân thủ chính sách vận hành.

## 14. Đọc số liệu để tìm nguyên nhân thay vì chỉ nhìn tổng dung lượng

Một quy trình điều tra thực tế:

1. Ghi lại mức Class/Metaspace sau startup ổn định.
2. Ghi lại sau khi triển khai plugin hoặc nạp module.
3. Thực hiện thao tác unload/redeploy theo quy trình bình thường.
4. Cho workload và GC có thời gian hoàn tất.
5. Chụp lại VM.metaspace, đặc biệt là thống kê theo loader.
6. So sánh số loader, số class, used, committed và reserved.
7. Nếu loader cũ còn tồn tại, tìm tham chiếu giữ loader bằng heap dump hoặc công cụ phân tích phù hợp.
8. Nếu loader đã unload nhưng committed memory chưa giảm ngay, xem xét chunk reuse, commit granule và thời điểm purge trước khi kết luận leak.

Một số tình huống:

| Quan sát | Cách diễn giải |
|---|---|
| Used tăng cùng số class tăng | Có thể ứng dụng đang nạp thêm class hợp lệ |
| Loader count tăng qua mỗi redeploy và không giảm | Nghi ngờ class loader leak |
| Used giảm sau unload nhưng committed còn cao | Vùng đã rảnh có thể được giữ để tái sử dụng; chưa đủ bằng chứng leak |
| Reserved cao nhưng committed thấp | JVM đang giữ address space nhưng không backing toàn bộ bằng memory |
| Class category tăng nhưng thống kê loader không giải thích hết | Kiểm tra compressed class space, cấu trúc VM và giới hạn của công cụ |

Không yêu cầu committed memory phải giảm về đúng mức ban đầu ngay sau mỗi lần unload. JVM có thể giữ một phần vùng đã commit để tái sử dụng nhằm tránh liên tục commit/uncommit khi workload lặp lại.

## 15. Điều chỉnh MaxMetaspaceSize có phải cách sửa phân mảnh?

Không. MaxMetaspaceSize là giới hạn trên cho lượng native memory dành cho class metadata. Nó không thay đổi thuật toán buddy allocator và không chữa class loader leak.

Ví dụ cấu hình giới hạn:

~~~text
java -XX:MaxMetaspaceSize=512m -jar app.jar
~~~

Chỉ đặt giới hạn khi đã đo mức sử dụng thực tế và hiểu workload. Nếu ứng dụng hợp lệ cần nhiều metadata hơn, giới hạn quá thấp có thể làm phát sinh OutOfMemoryError: Metaspace. Nếu loader bị giữ lại, tăng giới hạn chỉ kéo dài thời gian trước khi lỗi xảy ra.

Các tuning flag nội bộ hoặc hướng dẫn cũ về allocator trước Java 16 không nên được sao chép máy móc sang JVM hiện tại. Trước khi dùng một cờ -XX cụ thể, hãy kiểm tra tài liệu của đúng nhà cung cấp và phiên bản runtime đang triển khai.

## 16. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Metaspace nằm trong Java heap | Metaspace là native memory; object Class vẫn là heap object |
| Tăng heap sẽ sửa OOME Metaspace | Heap và metaspace là các vùng khác nhau |
| Gọi close() class loader sẽ unload mọi class | close() giải phóng một số tài nguyên; loader vẫn phải unreachable và chờ GC |
| Chunk rảnh luôn lập tức trả RAM cho OS | Chunk có thể được giữ để tái sử dụng; uncommit phụ thuộc granule và chính sách |
| Buddy allocator loại bỏ mọi phân mảnh | Nó giảm phân mảnh ở tầng chunk, không giải phóng metadata của loader còn sống |
| Reserved memory bằng RAM đã dùng | Reserved address space khác committed memory |
| Committed giảm chậm chắc chắn là memory leak | Cần đối chiếu used, loader count, thời điểm GC và chunk reuse |
| Tăng MaxMetaspaceSize là sửa class loader leak | Nó chỉ tăng giới hạn, không loại bỏ tham chiếu giữ loader |
| Mọi chi tiết chunk/granule là API ổn định | Đây là chi tiết triển khai HotSpot và có thể thay đổi |

## 17. Checklist review và vận hành

- [ ] Phân biệt rõ Java heap với native metaspace.
- [ ] Xác định class loader sở hữu metadata và vòng đời của loader.
- [ ] Khi unload plugin/redeploy, đóng tài nguyên và xóa mọi strong reference tới loader.
- [ ] Không coi close() là bằng chứng class đã unload.
- [ ] Theo dõi xu hướng class count và class loader count qua nhiều chu kỳ.
- [ ] Phân biệt reserved, committed và used.
- [ ] Hiểu chunk là đơn vị trung gian cho arena, không phải một class.
- [ ] Hiểu buddy allocator chia/ghép chunk để giảm phân mảnh ngoại vi.
- [ ] Hiểu commit granule hỗ trợ commit/uncommit backing memory.
- [ ] Dùng jcmd VM.metaspace để xem thống kê theo loader khi cần.
- [ ] Chỉ dùng NMT khi đã bật từ lúc JVM khởi động và hiểu overhead/phạm vi theo dõi.
- [ ] Không tăng MaxMetaspaceSize trước khi điều tra class loader lifecycle.
- [ ] Không sao chép tuning flag cũ mà chưa xác minh trên JDK đang chạy.

## 18. Ghi nhớ

- Metaspace lưu class metadata trong native memory, tách biệt với Java heap.
- Metadata gắn với class loader; class loader chỉ được unload khi không còn reachable và GC thực hiện class unloading.
- Arena cấp phát metadata từ các chunk để giảm chi phí của từng allocation nhỏ.
- Buddy allocator chia chunk lớn khi cần và ghép các buddy rảnh khi có thể.
- Commit/uncommit quản lý backing memory; reserved address space không đồng nghĩa RAM đã dùng.
- Elastic Metaspace từ Java 16 cải thiện khả năng commit theo nhu cầu và trả lại memory không còn dùng sau class unloading.
- Cơ chế mới giảm phân mảnh nhưng không thể thu hồi metadata của class loader còn sống.
- jcmd VM.metaspace và Native Memory Tracking là công cụ hiện hành để quan sát metaspace/native memory.
- MaxMetaspaceSize vẫn là giới hạn hữu ích khi được đặt dựa trên số liệu; nó không chữa class loader leak.
- Kích thước chunk, commit granule và các chi tiết allocator là triển khai nội bộ, không phải API để ứng dụng phụ thuộc.

Elastic Metaspace giúp HotSpot sử dụng native memory hiệu quả hơn bằng cách quản lý chunk linh hoạt, commit theo nhu cầu và uncommit vùng backing memory không còn cần. Tuy vậy, yếu tố quan trọng nhất vẫn là vòng đời class loader: khi loader cũ được giải phóng đúng cách, allocator mới có thể tái sử dụng và thu hồi các chunk mà loader đó từng sở hữu.

## Tài liệu tham khảo

- [JEP 387: Elastic Metaspace](https://openjdk.org/jeps/387) — mục tiêu và thay đổi chính được đưa vào Java 16.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — lệnh VM.metaspace và VM.native_memory cùng các tùy chọn hiện hành.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — MaxMetaspaceSize và NativeMemoryTracking.
- [Java Virtual Machine Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html) — cách bật NMT, baseline và đọc thống kê native memory.
- [OpenJDK Elastic Metaspace Review Guide](https://cr.openjdk.org/~stuefe/jep387/review-guide.html) — mô hình arena, chunk, buddy allocator và commit granules ở mức triển khai.
