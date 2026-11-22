# Đọc các cột jstat trong Java

**jstat** là công cụ dòng lệnh của JDK dùng để lấy mẫu thống kê hiệu năng và mức sử dụng tài nguyên của một Java HotSpot VM đang chạy. Công cụ đặc biệt hữu ích khi cần quan sát heap, các vùng của garbage collector (GC), số lần GC, thời gian GC, metaspace, class loading và JIT compilation.

Tên cột của jstat là các chữ viết tắt như S0C, EU, O, YGC, YGCT, FGC và GCT. Muốn đọc đúng kết quả, cần hiểu cột thuộc nhóm số liệu nào, đơn vị là gì, giá trị là tức thời hay tích lũy và sự thay đổi giữa các lần lấy mẫu nói lên điều gì.

Bài này tập trung vào cách đọc từng nhóm cột, liên hệ các cột với nhau và dùng chuỗi mẫu để nhận biết xu hướng. Danh sách tùy chọn và định dạng output có thể thay đổi theo JDK, nền tảng và JVM. Luôn kiểm tra danh sách tùy chọn trên máy đích bằng jstat -options trước khi dùng.

## 1. jstat đo những gì?

jstat dùng instrumentation có sẵn trong HotSpot VM để hiển thị thống kê về hiệu năng và tài nguyên của ứng dụng đang chạy. Các nhóm dữ liệu thường gặp:

- **Heap và GC**: dung lượng, mức sử dụng của Eden, Survivor và Old Generation.
- **GC counters**: số lần Young GC, Full GC và thời gian đã tiêu tốn cho GC.
- **Metaspace**: dung lượng đã commit và dung lượng đang sử dụng.
- **Compressed Class Space**: dung lượng dành cho class metadata nén.
- **Class loading**: số class đã nạp, đã unload và thời gian xử lý.
- **JIT compiler**: số tác vụ biên dịch, lỗi biên dịch và method vừa được biên dịch.

jstat phù hợp để quan sát xu hướng theo thời gian. Một dòng output là một mẫu tại một thời điểm; nhiều dòng liên tiếp cho biết các bộ đếm và vùng bộ nhớ thay đổi ra sao.

jstat không tự giải thích nguyên nhân của một vấn đề. Ví dụ, tỷ lệ Old Generation tăng có thể do promotion bình thường, workload thay đổi hoặc object bị giữ lại ngoài dự kiến. Cần đối chiếu nhiều cột, workload và các công cụ chẩn đoán khác trước khi kết luận.

## 2. Cú pháp lấy mẫu và chọn JVM

Cú pháp tổng quát:

~~~bash
jstat -<statOption> [-t] [-h n] <vmid> [interval [count]]
~~~

Trong đó:

- statOption chọn nhóm số liệu cần hiển thị.
- -t thêm cột thời gian kể từ lúc JVM khởi chạy.
- -h n in lại header sau mỗi n mẫu.
- vmid xác định JVM đích.
- interval là khoảng cách giữa các mẫu.
- count là số mẫu cần lấy.

Ví dụ lấy 10 mẫu GC utilization, mỗi giây một mẫu:

~~~bash
jstat -gcutil 2125 1000 10
~~~

Ví dụ thêm thời gian và in lại header sau mỗi 5 dòng:

~~~bash
jstat -gcutil -t -h 5 2125 1000 10
~~~

Nếu bỏ count, jstat tiếp tục lấy mẫu cho tới khi JVM kết thúc hoặc người vận hành dừng lệnh. Nếu bỏ interval, lệnh chỉ in một mẫu.

Đơn vị mặc định của interval là milliseconds. Có thể chỉ định đơn vị giây hoặc milliseconds theo cú pháp được JDK hiện tại hỗ trợ. Giá trị interval và count phải là số dương.

### Tìm JVM đích

Dùng jps:

~~~bash
jps -l
~~~

Ví dụ:

~~~text
2125 com.acme.JstatDemo
5485 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

2125 là ví dụ LVMID. LVMID thường là PID của hệ điều hành nhưng không được bảo đảm luôn trùng PID OS. jps cũng có thể không liệt kê JVM chạy trong một Docker process riêng biệt; khi đó cần xác định LVMID trong đúng môi trường hoặc PID namespace.

Có thể kiểm tra process bằng công cụ hệ điều hành. Trên Linux:

~~~bash
ps -eo pid,user,group,args
~~~

Trên Windows, dùng Task Manager hoặc PowerShell để đối chiếu process ID và command line.

jstat thường được dùng trên JVM cục bộ. Với remote monitoring, VMID có thể chỉ định hostname và cần jstatd ở máy đích. Không bật dịch vụ remote monitoring tùy tiện; cần kiểm soát mạng, tài khoản và chính sách truy cập.

## 3. Xem danh sách statOption khả dụng

Trước khi chọn cột, chạy:

~~~bash
jstat -options
~~~

Lệnh này liệt kê các statOption được cài đặt jstat trên nền tảng hiện tại hỗ trợ.

Các tùy chọn phổ biến gồm:

| Tùy chọn | Nhóm thống kê |
|---|---|
| -class | Class loader |
| -compiler | JIT compiler |
| -gc | Dung lượng và mức sử dụng heap cùng bộ đếm GC |
| -gccapacity | Capacity của các generation và space |
| -gccause | GC utilization và nguyên nhân GC gần nhất/hiện tại |
| -gcnew | Hoạt động của New Generation |
| -gcnewcapacity | Capacity của New Generation |
| -gcold | Old Generation và metaspace |
| -gcoldcapacity | Capacity của Old Generation |
| -gcmetacapacity | Capacity của metaspace |
| -gcutil | Tóm tắt utilization theo phần trăm |
| -printcompilation | Thông tin method compilation gần nhất |

Không phải JVM hoặc collector nào cũng cung cấp mọi nhóm số liệu theo cùng cách. Nếu một option không xuất hiện trong jstat -options, không giả định rằng có thể dùng nó trên máy đó.

## 4. Quy ước đọc tên cột

Các tên cột của jstat thường được ghép từ chữ viết tắt:

- C: Capacity, dung lượng hiện tại hoặc dung lượng tối đa tùy cột.
- U: Used, dung lượng đang sử dụng.
- MN: Minimum, dung lượng tối thiểu.
- MX: Maximum, dung lượng tối đa.
- S0 và S1: Survivor Space 0 và Survivor Space 1.
- E: Eden.
- O: Old Generation/Old Space.
- M: Metaspace.
- CCS: Compressed Class Space.
- YGC: Young Garbage Collection count.
- FGC: Full Garbage Collection count.
- T: Time hoặc threshold tùy nhóm cột.

Ví dụ:

| Cột | Cách hiểu |
|---|---|
| S0C | Capacity hiện tại của Survivor Space 0 |
| S0U | Dung lượng đang dùng trong Survivor Space 0 |
| EC | Capacity hiện tại của Eden |
| EU | Dung lượng đang dùng trong Eden |
| OC | Capacity hiện tại của Old Space |
| OU | Dung lượng đang dùng trong Old Space |
| MC | Metaspace committed |
| MU | Metaspace đang sử dụng |
| YGC | Số sự kiện Young GC |
| YGCT | Tổng thời gian Young GC |

C và U thường đi thành cặp để so sánh dung lượng hiện có với mức sử dụng. Nếu cần phần trăm sử dụng, có thể đọc cột tương ứng trong -gcutil hoặc tự tính Used/Capacity × 100 khi hai cột cùng đo một vùng.

## 5. Đọc nhóm -gc: dung lượng và mức sử dụng

Lệnh:

~~~bash
jstat -gc 2125 1000 10
~~~

Nhóm -gc hiển thị dung lượng và mức sử dụng của Survivor, Eden, Old Space, Metaspace, Compressed Class Space cùng các bộ đếm GC.

Các cột phổ biến:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| S0C | Capacity hiện tại của Survivor Space 0 | KB |
| S1C | Capacity hiện tại của Survivor Space 1 | KB |
| S0U | Dung lượng đang dùng ở Survivor Space 0 | KB |
| S1U | Dung lượng đang dùng ở Survivor Space 1 | KB |
| EC | Capacity hiện tại của Eden | KB |
| EU | Dung lượng đang dùng ở Eden | KB |
| OC | Capacity hiện tại của Old Space | KB |
| OU | Dung lượng đang dùng ở Old Space | KB |
| MC | Metaspace committed size | KB |
| MU | Metaspace utilization | KB |
| CCSC | Compressed Class Space committed size | KB |
| CCSU | Compressed Class Space used | KB |
| YGC | Số Young GC đã xảy ra | Lần |
| YGCT | Tổng thời gian Young GC | Giây |
| FGC | Số Full GC đã xảy ra | Lần |
| FGCT | Tổng thời gian Full GC | Giây |
| GCT | Tổng thời gian GC | Giây |

### Capacity và Used

Ví dụ:

~~~text
S0C    S1C    S0U    S1U    EC      EU      OC      OU
512.0  512.0  120.0  0.0    8192.0  6144.0  32768.0  12288.0
~~~

Đọc kết quả:

- Survivor 0 có capacity 512 KB, đang dùng 120 KB.
- Survivor 1 có capacity 512 KB, đang dùng 0 KB.
- Eden có capacity 8.192 KB, đang dùng 6.144 KB.
- Old Space có capacity 32.768 KB, đang dùng 12.288 KB.

Các số trên chỉ là ví dụ minh họa. Không nên cộng tất cả capacity trong một dòng để suy ra toàn bộ RAM của process; heap dump, metaspace, thread stack và native memory là những phạm vi khác nhau.

### Metaspace và Compressed Class Space

MC/MU và CCSC/CCSU là hai nhóm riêng:

- MC là lượng metaspace đã commit.
- MU là lượng metaspace đang sử dụng.
- CCSC là compressed class space đã commit.
- CCSU là compressed class space đang sử dụng.

Metaspace chứa metadata của class trong native memory. Nó không phải một phần của Java heap như object thông thường. CCS là vùng liên quan tới compressed class pointers khi JVM sử dụng cơ chế này.

Nếu MU hoặc CCSU tăng liên tục qua nhiều mẫu, hãy xem xét class loading, class unloading, dynamic proxy, generated class hoặc class loader lifecycle. Một lần tăng đơn lẻ không đủ để kết luận class loader leak.

## 6. Đọc nhóm -gcutil: phần trăm sử dụng

Lệnh:

~~~bash
jstat -gcutil 2125 1000 10
~~~

-gcutil là nhóm phổ biến để quan sát nhanh mức sử dụng của các vùng heap và bộ đếm GC.

Các cột:

| Cột | Ý nghĩa |
|---|---|
| S0 | Phần trăm sử dụng Survivor Space 0 trên capacity hiện tại |
| S1 | Phần trăm sử dụng Survivor Space 1 trên capacity hiện tại |
| E | Phần trăm sử dụng Eden trên capacity hiện tại |
| O | Phần trăm sử dụng Old Space trên capacity hiện tại |
| M | Phần trăm sử dụng Metaspace trên capacity hiện tại |
| CCS | Phần trăm sử dụng Compressed Class Space |
| YGC | Số Young GC |
| YGCT | Tổng thời gian Young GC, giây |
| FGC | Số Full GC |
| FGCT | Tổng thời gian Full GC, giây |
| GCT | Tổng thời gian GC, giây |

Ví dụ:

~~~text
S0     S1     E      O      M      CCS    YGC   YGCT    FGC   FGCT   GCT
0.00   75.00  82.00  40.00  65.00  45.00  10    0.450   1     0.100  0.550
0.00   75.00  98.00  40.00  65.00  45.00  10    0.450   1     0.100  0.550
75.00  0.00   2.00   42.00  65.00  45.00  11    0.470   1     0.100  0.570
~~~

Cách đọc:

- E tăng từ 82% lên 98% trước Young GC.
- Sau GC, E giảm về 2%.
- YGC tăng từ 10 lên 11.
- S0/S1 đổi vai trò sử dụng; một Survivor Space nhận các object sống sót.
- O tăng từ 40% lên 42%, có thể do một số object được promote lên Old Generation.
- GCT tăng từ 0,550 lên 0,570 giây, nghĩa là tổng thời gian GC tích lũy tăng thêm 0,020 giây.

Đây là dữ liệu mô phỏng để minh họa cách đọc, không phải kết quả đo của một JVM cụ thể.

### Vì sao E thường tăng rồi giảm?

Ứng dụng tạo object mới trong Eden. Khi Eden gần đầy, Young GC có thể xảy ra. Object còn sống được chuyển sang Survivor hoặc promote lên Old Generation; object không còn reachable được thu hồi. Vì vậy, E thường tăng dần giữa hai lần Young GC rồi giảm sau collection.

### Vì sao S0 và S1 thay phiên nhau?

Trong generational collector kiểu copying, hai Survivor Space có thể luân phiên làm vùng nguồn và vùng đích sau mỗi Young GC. Vì vậy S0 có thể đang được dùng ở mẫu này nhưng gần như rỗng ở mẫu tiếp theo, trong khi S1 tăng lên. Không kết luận bất thường chỉ vì một cột S0/S1 đổi mạnh giữa hai mẫu.

### Vì sao O tăng?

Object sống qua nhiều Young GC có thể được promote sang Old Generation. O tăng sau Young GC có thể là hành vi bình thường. Điều cần quan sát là O sau nhiều chu kỳ GC có giảm, ổn định hay tiếp tục tăng.

Nếu O tăng dần và không giảm sau các collection phù hợp, hãy điều tra live set, cache, collection, listener và object reference bằng heap dump hoặc JFR. jstat chỉ cho biết xu hướng utilization, không xác định object nào đang giữ bộ nhớ.

## 7. Đọc nhóm -gccause: thêm nguyên nhân GC

Lệnh:

~~~bash
jstat -gccause 2125 1000 10
~~~

-gccause hiển thị các cột giống -gcutil và thêm:

| Cột | Ý nghĩa |
|---|---|
| LGCC | Nguyên nhân của lần GC gần nhất |
| GCC | Nguyên nhân của GC hiện tại, nếu có |

Các giá trị nguyên nhân có thể khác nhau theo collector và JDK. Một số chuỗi có thể mô tả allocation failure, explicit GC hoặc một loại collection cụ thể.

Ví dụ minh họa:

~~~text
S0 S1 E O M CCS YGC YGCT FGC FGCT GCT LGCC              GCC
0  70 80 45 60 40 12  0.5  1   0.1  0.6 Allocation Failure No GC
~~~

Cách dùng:

- Xem LGCC để hiểu sự kiện gần nhất được kích hoạt bởi nguyên nhân nào.
- Xem GCC khi muốn biết JVM đang báo nguyên nhân của collection hiện tại.
- Đối chiếu với thời điểm YGC hoặc FGC tăng.
- Không suy luận rằng mọi Allocation Failure đều là lỗi; đây có thể là trigger bình thường khi vùng cấp phát cần được thu hồi.

Nếu thấy explicit GC lặp lại, kiểm tra code gọi System.gc(), framework hoặc cấu hình runtime. Không tắt explicit GC chỉ dựa vào một dòng jstat; cần xác minh nguyên nhân và tác động trước.

## 8. Đọc nhóm -gccapacity: capacity của các generation

Lệnh:

~~~bash
jstat -gccapacity 2125 1000 10
~~~

Nhóm này tập trung vào dung lượng của New Generation, Old Generation, Survivor, Eden, Metaspace và Compressed Class Space.

Các cột phổ biến:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| NGCMN | Capacity tối thiểu của New Generation | KB |
| NGCMX | Capacity tối đa của New Generation | KB |
| NGC | Capacity hiện tại của New Generation | KB |
| S0C | Capacity hiện tại của Survivor 0 | KB |
| S1C | Capacity hiện tại của Survivor 1 | KB |
| EC | Capacity hiện tại của Eden | KB |
| OGCMN | Capacity tối thiểu của Old Generation | KB |
| OGCMX | Capacity tối đa của Old Generation | KB |
| OGC | Capacity hiện tại của Old Generation | KB |
| OC | Capacity hiện tại của Old Space | KB |
| MCMN | Capacity tối thiểu của Metaspace | KB |
| MCMX | Capacity tối đa của Metaspace | KB |
| MC | Metaspace committed size | KB |
| CCSMN | Capacity tối thiểu của Compressed Class Space | KB |
| CCSMX | Capacity tối đa của Compressed Class Space | KB |
| CCSC | Compressed Class Space committed size | KB |
| YGC | Số Young GC | Lần |
| FGC | Số Full GC | Lần |

Capacity không phải lượng object đang sống. Đọc NGC hoặc OGC để biết vùng nhớ được cấp hiện tại; đọc EU/OU hoặc phần trăm E/O để hiểu mức sử dụng.

Ví dụ:

~~~text
NGCMN  NGCMX    NGC     S0C    S1C     EC     OGCMN  OGCMX    OGC      OC
1024.0  65536.0  8192.0  512.0  512.0   7168.0  4096.0  131072.0  32768.0  32768.0
~~~

Trong ví dụ, New Generation hiện có capacity 8 MB và có thể mở rộng tới 64 MB theo giới hạn hiển thị; Old Generation hiện có capacity 32 MB và maximum 128 MB.

Các giá trị minh họa có thể phụ thuộc collector và cách JVM biểu diễn generation. Không áp dụng mô hình New/Old Generation giống nhau cho mọi collector.

## 9. Đọc nhóm -gcnew: hoạt động của New Generation

Lệnh:

~~~bash
jstat -gcnew 2125 1000 10
~~~

-gcnew tập trung vào Eden và Survivor Space, cùng thông tin về tenuring.

Các cột:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| S0C | Capacity Survivor 0 | KB |
| S1C | Capacity Survivor 1 | KB |
| S0U | Survivor 0 đang dùng | KB |
| S1U | Survivor 1 đang dùng | KB |
| TT | Tenuring threshold hiện tại | Số chu kỳ tuổi |
| MTT | Maximum tenuring threshold | Số chu kỳ tuổi |
| DSS | Desired survivor size | KB |
| EC | Capacity Eden | KB |
| EU | Eden đang dùng | KB |
| YGC | Số Young GC | Lần |
| YGCT | Tổng thời gian Young GC | Giây |

### TT và MTT

Tenuring threshold là ngưỡng tuổi được dùng để quyết định khi nào object sống sót đủ lâu có thể được promote sang Old Generation. Tuổi object được tính theo số lần sống sót qua các collection liên quan, không phải số giây.

MTT là maximum tenuring threshold. TT thực tế có thể thay đổi động theo tình trạng Survivor Space và dữ liệu sống sót.

### DSS

DSS là desired survivor size, tức kích thước Survivor mà JVM mong muốn sử dụng theo chính sách GC. Nếu lượng object sống sót vượt mức phù hợp, JVM có thể điều chỉnh TT để promote object sớm hơn.

### Ví dụ

~~~text
S0C   S1C   S0U   S1U   TT  MTT  DSS   EC       EU      YGC  YGCT
512.0 512.0 80.0  0.0   15  15   256.0 8192.0  7000.0  20   0.620
512.0 512.0 0.0   190.0  2  15   256.0 8192.0  120.0   21   0.645
~~~

Sau Young GC, EU giảm mạnh và S1U tăng. TT từ 15 xuống 2 trong ví dụ, cho thấy JVM có thể đang giảm tuổi tối đa trước khi promote object do áp lực Survivor. Đây là ví dụ minh họa; muốn kết luận cần quan sát thêm các mẫu và collector thực tế.

## 10. Đọc nhóm -gcnewcapacity: giới hạn vùng New Generation

Lệnh:

~~~bash
jstat -gcnewcapacity 2125 1000 10
~~~

Các cột thường gặp:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| NGCMN | Capacity tối thiểu của New Generation | KB |
| NGCMX | Capacity tối đa của New Generation | KB |
| NGC | Capacity hiện tại của New Generation | KB |
| S0CMX | Maximum capacity Survivor 0 | KB |
| S0C | Capacity hiện tại Survivor 0 | KB |
| S1CMX | Maximum capacity Survivor 1 | KB |
| S1C | Capacity hiện tại Survivor 1 | KB |
| ECMX | Maximum capacity Eden | KB |
| EC | Capacity hiện tại Eden | KB |
| YGC | Số Young GC | Lần |
| FGC | Số Full GC | Lần |

Nhóm này trả lời câu hỏi về giới hạn và capacity của New Generation. Nó không cho biết trực tiếp bao nhiêu object đang sống; muốn biết mức sử dụng, đọc -gc hoặc -gcnew.

Nếu NGC tiến gần NGCMX trong khi EU thường xuyên cao và YGC tăng nhanh, có thể cần xem xét heap sizing hoặc allocation pressure. Không tự động tăng heap chỉ dựa vào capacity; cần đối chiếu với live set, thời gian GC và giới hạn RAM/container.

## 11. Đọc nhóm -gcold: Old Generation và metaspace

Lệnh:

~~~bash
jstat -gcold 2125 1000 10
~~~

Các cột phổ biến:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| MC | Metaspace committed size | KB |
| MU | Metaspace utilization | KB |
| CCSC | Compressed Class Space committed size | KB |
| CCSU | Compressed Class Space used | KB |
| OC | Capacity Old Space | KB |
| OU | Old Space đang dùng | KB |
| YGC | Số Young GC | Lần |
| FGC | Số Full GC | Lần |
| FGCT | Tổng thời gian Full GC | Giây |
| GCT | Tổng thời gian GC | Giây |

-gcold giúp quan sát hai mảng khác nhau trong cùng một output:

- Old Space: OC và OU.
- Class metadata: MC/MU và CCSC/CCSU.

Không nhầm MU với OU. MU là mức sử dụng Metaspace; OU là mức sử dụng Old Space. Metaspace nằm ngoài Java heap.

Nếu MU tăng liên tục, kiểm tra số class đã nạp, số class unload và class loader lifecycle. Nếu OU tăng sau mỗi chu kỳ GC và không giảm, cần điều tra object còn sống và promotion.

## 12. Đọc nhóm -gcoldcapacity: capacity của Old Generation

Lệnh:

~~~bash
jstat -gcoldcapacity 2125 1000 10
~~~

Các cột:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| OGCMN | Capacity tối thiểu Old Generation | KB |
| OGCMX | Capacity tối đa Old Generation | KB |
| OGC | Capacity hiện tại Old Generation | KB |
| OC | Capacity hiện tại Old Space | KB |
| YGC | Số Young GC | Lần |
| FGC | Số Full GC | Lần |
| FGCT | Tổng thời gian Full GC | Giây |
| GCT | Tổng thời gian GC | Giây |

Ví dụ output:

~~~text
Timestamp  OGCMN  OGCMX    OGC      OC      YGC  FGC  FGCT  GCT
150.1      1408.0 60544.0  11696.0  11696.0 194  80   2.874 3.799
150.4      1408.0 60544.0  13820.0  13820.0 194  81   2.938 3.863
150.7      1408.0 60544.0  13820.0  13820.0 194  81   2.938 3.863
~~~

Cách đọc:

- OGC tăng từ 11.696 KB lên 13.820 KB.
- FGC tăng từ 80 lên 81.
- FGCT tăng từ 2,874 giây lên 2,938 giây.
- GCT tăng từ 3,799 giây lên 3,863 giây.
- OGCMX vẫn là 60.544 KB, nên capacity hiện tại còn khả năng mở rộng theo giới hạn được báo cáo.

Capacity tăng không đồng nghĩa với leak. JVM có thể mở rộng generation để đáp ứng allocation hoặc promotion. Cần kiểm tra OU, tỷ lệ sử dụng, Full GC và xu hướng sau collection.

## 13. Đọc nhóm -gcmetacapacity: capacity của Metaspace

Lệnh:

~~~bash
jstat -gcmetacapacity 2125 1000 10
~~~

Các cột phổ biến:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| MCMN | Capacity tối thiểu của Metaspace | KB |
| MCMX | Capacity tối đa của Metaspace | KB |
| MC | Metaspace committed size | KB |
| CCSMN | Capacity tối thiểu Compressed Class Space | KB |
| CCSMX | Capacity tối đa Compressed Class Space | KB |
| YGC | Số Young GC | Lần |
| FGC | Số Full GC | Lần |
| FGCT | Tổng thời gian Full GC | Giây |
| GCT | Tổng thời gian GC | Giây |

Dùng nhóm này khi điều tra:

- Ứng dụng tạo nhiều class động.
- Framework proxy hoặc bytecode generation.
- ClassLoader được tạo liên tục.
- Metaspace tăng theo thời gian.
- Class unloading không diễn ra như dự kiến.

MC là committed capacity, không phải số byte metadata đang thực sự được sử dụng. Để xem mức sử dụng, đối chiếu MU trong -gc hoặc -gcold.

Nếu MC tăng nhưng MU ổn định, JVM có thể đã commit thêm vùng nhớ. Nếu MU tăng liên tục cùng Loaded tăng và Unloaded không tăng tương ứng, cần kiểm tra class loader và dynamic class generation.

## 14. Đọc nhóm -class: thống kê class loading

Lệnh:

~~~bash
jstat -class 2125 1000 10
~~~

Các cột:

| Cột | Ý nghĩa | Đơn vị |
|---|---|---|
| Loaded | Tổng số class đã được nạp | Class |
| Bytes | Tổng lượng dữ liệu class đã nạp | KB |
| Unloaded | Tổng số class đã unload | Class |
| Bytes | Tổng lượng dữ liệu class đã unload | KB |
| Time | Thời gian đã dùng cho class loading/unloading | Giây |

Ví dụ:

~~~text
Loaded  Bytes   Unloaded  Bytes  Time
8500    12400.0 120       180.0  4.250
8550    12520.0 120       180.0  4.280
8600    12650.0 140       205.0  4.310
~~~

Các bộ đếm Loaded và Unloaded thường là giá trị tích lũy. Khi Loaded tăng nhanh, ứng dụng có thể đang nạp nhiều class mới. Điều này có thể bình thường khi startup, warm-up hoặc nạp plugin.

Nếu class loading tiếp tục tăng trong thời gian dài, kết hợp với Metaspace tăng và class unload thấp, hãy kiểm tra:

- Tạo class động hoặc proxy liên tục.
- Framework tạo class theo request.
- ClassLoader được tạo mà không được giải phóng.
- Plugin reload nhưng class loader cũ vẫn còn reachable.
- Cấu hình redeploy hoặc application server.

Loaded lớn không tự động có nghĩa là class loader leak. Cần xem class loader nào giữ class và liệu class loader cũ có thể được thu hồi không.

## 15. Đọc nhóm -compiler và -printcompilation

### -compiler

Lệnh:

~~~bash
jstat -compiler 2125 1000 10
~~~

Các cột:

| Cột | Ý nghĩa |
|---|---|
| Compiled | Số tác vụ biên dịch đã thực hiện |
| Failed | Số tác vụ biên dịch thất bại |
| Invalid | Số kết quả biên dịch bị invalidated |
| Time | Tổng thời gian thực hiện các tác vụ biên dịch, giây |
| FailedType | Loại compilation của lần lỗi gần nhất |
| FailedMethod | Class và method liên quan lần lỗi gần nhất |

Compiled và Time thường tăng trong quá trình JVM warm-up khi JIT biên dịch các method nóng. Failed tăng cần được xem xét cùng FailedType và FailedMethod; một số lỗi hoặc invalidation có thể là hoạt động nội bộ bình thường, không phải lỗi ứng dụng ngay lập tức.

### -printcompilation

Lệnh:

~~~bash
jstat -printcompilation 2125 1000 10
~~~

Các cột:

| Cột | Ý nghĩa |
|---|---|
| Compiled | Số tác vụ biên dịch của method vừa được biên dịch gần nhất |
| Size | Số byte bytecode của method vừa được biên dịch |
| Type | Loại compilation |
| Method | Tên class và method vừa được biên dịch |

-printcompilation cho thông tin về method compilation gần nhất tại mỗi lần lấy mẫu. Nó không phải danh sách đầy đủ tất cả method đã được JIT biên dịch.

Class name trong Method có thể dùng dấu gạch chéo để phân tách package thay vì dấu chấm.

## 16. Đọc bộ đếm GC theo thời gian

Các cột YGC, YGCT, FGC, FGCT và GCT là bộ đếm/tổng thời gian tích lũy từ khi JVM khởi chạy.

| Cột | Ý nghĩa |
|---|---|
| YGC | Số Young GC đã xảy ra |
| YGCT | Tổng thời gian dành cho Young GC |
| FGC | Số Full GC đã xảy ra |
| FGCT | Tổng thời gian dành cho Full GC |
| GCT | Tổng thời gian GC |

Ví dụ hai lần lấy mẫu cách nhau 10 giây:

~~~text
Sample  YGC  YGCT   FGC  FGCT  GCT
1       100  2.500  2    0.800 3.300
2       105  2.650  2    0.800 3.450
~~~

Trong khoảng lấy mẫu:

- Có thêm 5 Young GC.
- Tổng thời gian Young GC tăng 0,150 giây.
- Không có Full GC mới.
- Tổng thời gian GC tăng 0,150 giây.

Có thể tính tỷ lệ thời gian GC gần đúng trong khoảng:

~~~text
GC time delta / elapsed time * 100
0.150 / 10 * 100 = 1.5%
~~~

Đây là tỷ lệ thời gian GC tích lũy tăng trong khoảng lấy mẫu, không phải phép đo chính xác CPU utilization của toàn process. Khi interval quá ngắn, độ phân giải timestamp và lịch scheduling có thể làm tỷ lệ dao động.

### Phân biệt số lần GC và thời gian GC

YGC tăng nhanh nhưng YGCT tăng ít có thể nghĩa là nhiều Young GC ngắn. FGC tăng ít nhưng FGCT tăng mạnh có thể cho thấy Full GC tốn thời gian. Hãy xem cả count lẫn time thay vì chỉ nhìn một cột.

## 17. Đọc nhiều nhóm cột cùng nhau

Không nên đọc một cột riêng lẻ rồi kết luận về hiệu năng. Một số tổ hợp hữu ích:

| Quan sát | Cột nên xem cùng nhau | Hướng điều tra |
|---|---|---|
| Eden thường xuyên gần đầy | E, EU, EC, YGC, YGCT | Allocation rate và tần suất Young GC |
| Old Space tăng dần | O, OU, OC, FGC, FGCT | Promotion, live set, memory leak |
| Survivor thường xuyên đầy | S0, S1, S0U, S1U, TT, DSS | Object sống sót và promotion |
| Metaspace tăng | M, MU, MC, Loaded, Unloaded | Class loading và class loader lifecycle |
| Full GC lặp lại | FGC, FGCT, GCT, GCC, LGCC | Nguyên nhân Full GC và thời gian pause |
| Class tăng liên tục | Loaded, Unloaded, MU, CCSU | Dynamic class generation hoặc class loader leak |
| JIT compile tăng | Compiled, Time, Failed, Invalid | Warm-up và compilation activity |

### Ví dụ: allocation pressure

Nếu E liên tục tăng tới mức cao rồi giảm mạnh, YGC tăng đều và O gần như ổn định, ứng dụng có thể đang tạo nhiều object ngắn hạn. Cần xem allocation rate bằng JFR hoặc profiler trước khi thay đổi heap.

### Ví dụ: live set tăng

Nếu O tăng dần qua nhiều chu kỳ GC và không giảm tương ứng, có thể nhiều object đang được giữ sống. jstat chỉ cho thấy xu hướng. Dùng heap dump để tìm object dominator và Path to GC Roots.

### Ví dụ: class loader pressure

Nếu Loaded tăng liên tục, Unloaded gần như không đổi và MU/CCSU cũng tăng, cần kiểm tra framework tạo class, proxy, plugin hoặc class loader lifecycle. Chưa thể kết luận leak chỉ từ các counter này.

### Ví dụ: GC pause tăng

Nếu YGCT hoặc FGCT tăng nhanh so với thời gian chạy, hãy tính delta giữa các mẫu. Kết hợp JFR để xem thời lượng từng GC event, loại collector, allocation pressure và các pause khác.

## 18. Thực hành với jstat và một Java process

Ví dụ sau tạo một process Java 17+ cấp phát object liên tục và giữ lại một tập nhỏ byte array. Mục tiêu là tạo hoạt động allocation đủ để quan sát các cột Eden và Young GC.

Cấu trúc:

~~~text
project/
  src/
    com/acme/JstatDemo.java
  out/
~~~

Tệp src/com/acme/JstatDemo.java:

~~~java
package com.acme;

public final class JstatDemo {
    public static void main(String[] args) throws InterruptedException {
        byte[][] live = new byte[16][];

        System.out.println("READY");

        while (true) {
            for (int i = 0; i < live.length; i++) {
                live[i] = new byte[64 * 1024];
            }
            Thread.sleep(250);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/acme/JstatDemo.java
~~~

Chạy với heap giới hạn:

~~~bash
java -Xms64m -Xmx128m -cp out com.acme.JstatDemo
~~~

Stdout chính xác:

~~~text
READY
~~~

Process tiếp tục chạy và tạo khoảng 1 MB allocation mỗi 250 ms, đồng thời giữ lại 16 mảng byte mới nhất. Lượng cấp phát và tần suất GC thực tế phụ thuộc JVM, collector và máy.

Mở terminal thứ hai, xác định LVMID:

~~~bash
jps -l
~~~

Giả sử LVMID là 2125. Thực hành:

~~~bash
jstat -gcutil 2125 1000 10
jstat -gc 2125 1000 10
jstat -gcnew 2125 1000 10
jstat -gccause 2125 1000 10
jstat -class 2125 1000 10
jstat -compiler 2125 1000 10
~~~

Hãy quan sát:

1. E tăng trong thời gian cấp phát.
2. YGC tăng khi xảy ra Young GC.
3. E giảm sau collection.
4. S0/S1 có thể luân phiên nhận object sống sót.
5. O có thể tăng nếu object được promote.
6. YGCT và GCT tăng tích lũy.

Các con số cụ thể không cố định nên không thể đưa stdout số liệu jstat chính xác cho mọi máy. Chỉ dòng READY của chương trình là output cố định. Khi thực hành xong, nhấn Ctrl+C ở terminal chạy Java process để dừng chương trình.

## 19. Timestamp và lặp header

### Thêm timestamp với -t

~~~bash
jstat -gcutil -t 2125 1000 5
~~~

Timestamp là thời gian đã trôi qua tính bằng giây kể từ khi target JVM khởi chạy. Nó giúp đối chiếu mẫu jstat với log, metric và thời điểm incident.

Timestamp không phải giờ lịch. Muốn ghép với log theo thời gian thực, cần ghi nhận thời điểm bắt đầu chạy lệnh hoặc dùng hệ thống monitoring có timestamp riêng.

### In header định kỳ với -h

~~~bash
jstat -gcutil -h 5 2125 1000 20
~~~

Header được in lại sau mỗi 5 mẫu. Điều này hữu ích khi output dài hoặc được lưu thành log, vì người đọc có thể xác định lại tên cột sau nhiều dòng dữ liệu.

Có thể kết hợp -t và -h:

~~~bash
jstat -gcutil -t -h 5 2125 1000 20
~~~

## 20. Giới hạn và lưu ý khi diễn giải jstat

### jstat là công cụ HotSpot

jstat đọc instrumentation được cung cấp bởi HotSpot VM. Kết quả không phải một API Java chuẩn có cùng ý nghĩa trên mọi JVM implementation.

### Không phải mọi collector có cùng mô hình generation

Tên cột như Eden, Survivor và Old Generation phản ánh mô hình generational heap. Collector, JDK release và nền tảng có thể làm thay đổi cột khả dụng hoặc cách biểu diễn. Kiểm tra -options và tài liệu của đúng JDK đang chạy.

### Không viết parser phụ thuộc cứng vào output

Tài liệu jstat cảnh báo không nên viết script parse output vì định dạng có thể thay đổi trong các release tương lai. Nếu buộc phải tích hợp, hãy cô lập parser, kiểm tra version, xử lý cột thiếu và có test cho từng JDK mục tiêu. Với monitoring dài hạn, ưu tiên JMX metrics, JFR hoặc giải pháp metrics có schema ổn định.

### jstat là công cụ experimental và unsupported

Command reference mô tả jstat là experimental và unsupported; tùy chọn và chức năng có thể thay đổi hoặc bị loại bỏ. Không nên xây dựng nền tảng production phụ thuộc lâu dài vào output text của jstat.

### Instrumentation có giới hạn

Oracle lưu ý instrumentation của jstat không truy cập được trên FAT32. Ngoài ra, việc lấy mẫu có độ phân giải hữu hạn; interval quá ngắn có thể tạo nhiều output mà không đem lại thêm thông tin hữu ích.

### Không nhầm heap với toàn bộ process memory

jstat tập trung vào các counter và pool mà HotSpot instrumentation cung cấp. Nếu RSS tăng nhưng heap ổn định, cần xem direct memory, native allocation, metaspace, thread stack và OS metrics.

## 21. Dùng công cụ nào khi cần thông tin sâu hơn?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Lấy mẫu nhanh heap và GC | jstat |
| Xem command chẩn đoán JVM hiện có | jcmd PID help |
| Theo dõi event GC và pause theo thời gian | JFR và JDK Mission Control |
| Xem heap object graph | jcmd GC.heap_dump và Eclipse MAT |
| Theo dõi class loading và class unloading | jstat -class, JFR |
| Theo dõi native memory của HotSpot | Native Memory Tracking |
| Monitoring liên tục bằng metric | JMX hoặc metrics framework của ứng dụng |

jcmd là công cụ diagnostic command được Oracle khuyến nghị thay cho một số tiện ích cũ như jstack, jinfo và jmap; nó không thay thế trực tiếp mọi cột time-series của jstat. JFR/JMC phù hợp khi cần event timeline và phân tích chi tiết hơn.

JFR có template default với overhead thấp và profile thu thập nhiều dữ liệu hơn nhưng ảnh hưởng hiệu năng lớn hơn. Chọn template theo mục tiêu và thời gian thu thập.

## 22. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jstat không được nhận diện | PATH chưa chứa thư mục bin của JDK | Kiểm tra JAVA_HOME và PATH |
| Không thấy JVM trong jps | JVM ở Docker process riêng hoặc khác namespace | Dùng ps trong đúng namespace hoặc chạy công cụ trong container |
| LVMID không hoạt động như PID | LVMID không nhất thiết luôn trùng PID OS | Xác định lại bằng jps và công cụ OS |
| Instrumentation không truy cập được | Môi trường filesystem hoặc JVM không cung cấp dữ liệu | Kiểm tra filesystem, đặc biệt FAT32, và target JVM |
| Unknown option | Option không được hỗ trợ trên platform/JDK đó | Chạy jstat -options |
| Output thiếu cột mong đợi | Chọn sai statOption hoặc collector không cung cấp nhóm đó | Chọn option đúng và kiểm tra phiên bản |
| E luôn cao | Allocation pressure hoặc lấy mẫu ngay trước GC | Quan sát nhiều mẫu, YGC và YGCT |
| O tăng liên tục | Promotion hoặc object còn sống tăng | Kiểm tra sau GC, dùng heap dump để tìm reference |
| M tăng liên tục | Class metadata tăng hoặc class loader không được thu hồi | Đối chiếu Loaded/Unloaded và class loader lifecycle |
| FGC tăng nhanh | Full GC xảy ra thường xuyên | Dùng gccause và JFR để xác định nguyên nhân, pause |
| S0/S1 đổi mạnh giữa các mẫu | Survivor spaces luân phiên sau collection | Đọc cùng S0U/S1U, TT và YGC |
| Header bị mất khi log dài | Header chỉ in ở mẫu đầu | Dùng -h n |
| Script parse sai output | Định dạng hoặc cột thay đổi giữa JDK | Tránh parser brittle; kiểm tra version hoặc chuyển sang JMX/JFR |
| jstat không phản ánh RSS | Công cụ không đo đầy đủ native memory | Dùng NMT và công cụ hệ điều hành |

## 23. Quy trình đọc jstat trong thực tế

1. Xác định JDK và JVM implementation đang chạy.
2. Dùng jps hoặc công cụ OS tìm đúng LVMID/PID.
3. Chạy jstat -options để biết nhóm cột được hỗ trợ.
4. Bắt đầu bằng -gcutil để có bức tranh tổng quát.
5. Nếu cần dung lượng tuyệt đối, dùng -gc.
6. Nếu cần chi tiết New Generation, dùng -gcnew và -gcnewcapacity.
7. Nếu cần Old Generation, dùng -gcold và -gcoldcapacity.
8. Nếu cần metaspace, dùng -gcmetacapacity và đối chiếu -class.
9. Nếu cần nguyên nhân GC, dùng -gccause.
10. Nếu nghi ngờ class loading hoặc JIT, dùng -class, -compiler và -printcompilation.
11. Lấy nhiều mẫu với interval hợp lý; dùng -t và -h khi cần.
12. So sánh delta của YGC, FGC, YGCT, FGCT và GCT giữa các mẫu.
13. Đối chiếu số liệu với workload và thời điểm GC.
14. Dùng JFR, heap dump, JMX hoặc NMT nếu cần xác định nguyên nhân sâu hơn.
15. Ghi lại JDK version, collector, option, interval và thời điểm để người khác tái lập phép đo.

## 24. Ghi nhớ

- jstat đọc thống kê hiệu năng và resource consumption từ instrumentation của HotSpot.
- jstat không cần cờ khởi động đặc biệt; instrumentation có sẵn được bật mặc định trong HotSpot.
- Dùng jstat -options để xem các statOption khả dụng trên máy đích.
- -gc hiển thị capacity và used của Survivor, Eden, Old Space, Metaspace, CCS cùng bộ đếm GC.
- -gcutil hiển thị phần trăm sử dụng của S0, S1, E, O, M và CCS.
- -gccause thêm LGCC và GCC để xem nguyên nhân GC gần nhất và hiện tại.
- -gccapacity, -gcnewcapacity, -gcoldcapacity và -gcmetacapacity tập trung vào capacity.
- -gcnew giúp đọc S0/S1, TT, MTT, DSS, EC và EU.
- -class theo dõi class loading/unloading; -compiler và -printcompilation theo dõi JIT.
- YGC/FGC là bộ đếm tích lũy; YGCT/FGCT/GCT là thời gian GC tích lũy tính bằng giây.
- Dùng delta giữa các mẫu để hiểu tần suất và chi phí GC trong một khoảng thời gian.
- LVMID thường nhưng không luôn trùng PID OS.
- jstat là experimental/unsupported theo command reference; option và output có thể thay đổi.
- Không viết parser phụ thuộc cứng vào output text của jstat.
- jstat không đo toàn bộ RSS hoặc native memory; dùng NMT, JFR, JMX và OS tools khi cần.

## Tài liệu tham khảo chính thức

- [The jstat Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html)
- [Diagnostic Tools — JDK 26, The jstat Utility](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Java Flight Recorder — JDK 26 Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)