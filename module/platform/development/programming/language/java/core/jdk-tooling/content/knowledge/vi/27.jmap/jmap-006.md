# Dump format của jmap: HPROF heap dump

## 1. Heap dump là gì?

Heap dump là ảnh chụp Java heap của một JVM tại một thời điểm. File dump ghi lại các object, class, field, giá trị primitive, mối tham chiếu giữa object và thông tin cần thiết để phân tích object nào đang được giữ trong bộ nhớ.

Với HotSpot JDK, lệnh `jmap -dump:format=b` tạo heap dump dạng nhị phân HPROF (Heap/HPROF binary format). Đây là định dạng phổ biến để mở bằng Eclipse Memory Analyzer (MAT) và các công cụ phân tích heap tương thích.

Heap dump hữu ích khi:

- Điều tra memory leak và object bị giữ lại ngoài dự kiến.
- Tìm class hoặc loại object chiếm nhiều heap.
- Tìm đường tham chiếu từ Garbage Collection (GC) roots đến một object.
- Kiểm tra collection tăng không giới hạn, cache hoặc session giữ dữ liệu lâu.
- Phân tích trạng thái object sau một lần tăng bộ nhớ bất thường.

Cần phân biệt ba loại artifact:

| Artifact | Phạm vi | Dùng để làm gì |
|---|---|---|
| Java heap dump (HPROF) | Object và cấu trúc Java heap | Phân tích object, references, GC roots |
| OS core dump | Không gian địa chỉ tiến trình và trạng thái native ở mức hệ điều hành | Phân tích crash, native memory, JVM internals |
| Thread dump | Stack trace và trạng thái thread tại một thời điểm | Điều tra deadlock, block, request bị treo |

HPROF không phải bản sao toàn bộ RAM của tiến trình. Nó không chứa toàn bộ native allocation, shared library, register hay trạng thái hệ điều hành như core dump. Nó cũng không phải lịch sử allocation theo thời gian; nếu cần biết object được tạo ở đâu và lúc nào, hãy thu thập dữ liệu bằng Java Flight Recorder (JFR) hoặc profiler.

## 2. HPROF binary format là gì?

Tham số `format=b` yêu cầu `jmap` ghi heap dump dưới dạng binary HPROF. File không phải văn bản để đọc trực tiếp bằng Notepad hoặc editor thông thường. Các byte trong file được tổ chức thành header và chuỗi record có tag, timestamp và payload.

Với HotSpot JDK 24.0.2 được kiểm tra, header của file bắt đầu bằng chuỗi:

~~~text
JAVA PROFILE 1.0.2
~~~

Sau chuỗi header có byte kết thúc null, kích thước identifier, timestamp và các record. Một record HPROF có cấu trúc khái quát:

| Thành phần | Kích thước | Ý nghĩa |
|---|---:|---|
| TAG | 1 byte | Loại record |
| Time offset | 4 byte | Thời gian tương đối so với timestamp trong header |
| Body length | 4 byte | Số byte của payload |
| BODY | Theo độ dài | Nội dung của record |

Các record có thể mô tả tên UTF-8, class được load, stack frame, stack trace, thread, object, array, field và heap metadata. Identifier dùng để liên kết object, class, string và stack trace trong file; kích thước identifier được ghi trong header, vì vậy không nên tự giả định mọi identifier đều là 4 byte.

### HPROF 1.0.1 và 1.0.2

HPROF có nhiều phiên bản header. HPROF 1.0.2 bổ sung khả năng chia heap dump thành nhiều segment record, kết thúc bằng record báo hết dump. Cách chia segment giúp biểu diễn dump lớn mà không cần một record heap duy nhất.

Tài liệu phát hành của Oracle ghi nhận binary HPROF 1.0.2 được dùng cho heap dump nhị phân trên các bản JDK hiện đại. Tuy nhiên, hãy để parser tương thích xử lý header và record thay vì tự phân tích bằng offset cố định.

## 3. Cấu trúc file và nội dung HPROF

Một HPROF binary thường chứa:

- Class metadata: tên class, superclass, class loader và thông tin field.
- Object records: object instance và tham chiếu đến object khác.
- Primitive values: giá trị số hoặc boolean nằm trong field và primitive array.
- Array records: object array và primitive array.
- GC roots: các điểm bắt đầu mà GC dùng để xác định object còn reachable, ví dụ stack/local, static field hoặc JNI reference tùy loại root.
- Thread và stack information: dữ liệu thread, stack frame và stack trace có trong dump.
- Heap metadata: record mô tả trạng thái và cấu trúc heap.

HPROF là snapshot. Nó cho biết object tồn tại hoặc được ghi nhận trong snapshot và các tham chiếu của chúng. Nó không trực tiếp trả lời:

- Object được tạo ở dòng code nào nếu không có allocation trace riêng.
- Object đã tồn tại bao lâu.
- Một object đã được tạo bao nhiêu lần trong toàn bộ thời gian chạy.
- Native memory nào ngoài Java heap đang chiếm RAM.
- Một luồng đã thực hiện những thao tác gì trước thời điểm dump nếu không có dữ liệu trace khác.

Dùng JFR hoặc profiler để phân tích allocation theo thời gian; dùng native memory tracking, OS tools hoặc core dump khi câu hỏi nằm ngoài Java heap.

## 4. Tạo HPROF bằng jmap

Kiểm tra tùy chọn mà JDK đang cài hỗ trợ:

~~~bash
jmap -h
~~~

Cú pháp dump tổng quát:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Các tùy chọn chính:

| Tùy chọn | Ý nghĩa |
|---|---|
| `live` | Chỉ ghi các object còn sống (live) |
| `all` | Ghi toàn bộ object hiện có trong heap, kể cả object unreachable chưa được thu gom |
| `format=b` | Ghi binary HPROF |
| `file=<path>` | Đường dẫn file output |
| `gz=<1..9>` | Ghi HPROF trong gzip với mức nén từ 1 đến 9 trên JDK 24.0.2 được kiểm tra |

Ví dụ dump các object live:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

Dump toàn bộ object:

~~~bash
jmap "-dump:all,format=b,file=heap-all.hprof" <pid>
~~~

Nếu không chỉ định `live` hoặc `all`, help của JDK 24.0.2 cho biết mặc định là `all`. Nếu truyền cả hai, `live` có ưu tiên.

Tùy chọn `live` làm dump chỉ chứa object còn reachable theo trạng thái JVM tại lúc chụp. Tùy chọn `all` có thể giữ cả object không còn reachable nhưng vẫn đang hiện diện trong heap vì chưa được thu gom. Hai lựa chọn trả lời các câu hỏi khác nhau: `live` phù hợp xem object đang được giữ; `all` có thể hữu ích khi muốn quan sát cả object unreachable trước khi GC thu dọn.

Đừng nhầm mặc định của `jmap` với `jcmd GC.heap_dump`: mặc định của `jcmd` là dump live objects và yêu cầu full GC, trừ khi dùng `-all`.

## 5. Dump HPROF đã nén bằng gzip

Heap dump có thể lớn gần bằng dung lượng Java heap được ghi. Trên JDK 24.0.2, `jmap -h` có tùy chọn `gz`:

~~~bash
jmap "-dump:live,format=b,gz=1,file=heap-live.hprof.gz" <pid>
~~~

Các mức nén:

- `gz=1`: nén nhanh nhất, thường tốn ít CPU hơn.
- `gz=9`: nén mạnh hơn nhưng thường tốn CPU và thời gian hơn.
- Mức trung gian cân bằng thời gian tạo file và dung lượng lưu trữ.

Gzip chỉ bọc HPROF binary bên trong. Khi giải nén, header HPROF vẫn bắt đầu bằng `JAVA PROFILE 1.0.2`. File gzip thường có magic bytes `1F 8B`; có thể kiểm tra bằng công cụ gzip hoặc hex viewer.

Ví dụ kiểm tra file gzip:

~~~bash
gzip -t heap-live.hprof.gz
~~~

Không đổi phần mở rộng file để biến một HPROF thường thành gzip hoặc ngược lại. Phần mở rộng nên phản ánh nội dung thực tế, ví dụ `.hprof` cho binary HPROF và `.hprof.gz` cho HPROF được nén bằng gzip.

Nén giúp giảm disk usage và chi phí truyền file. Đổi lại, công cụ phân tích phải giải nén hoặc đọc luồng nén, có thể làm thời gian parse và truy vấn tăng lên.

## 6. Tạo histogram để kiểm tra trước khi dump

Nếu chỉ cần biết class nào có nhiều instance hoặc chiếm nhiều byte, có thể dùng histogram thay vì tạo heap dump lớn:

~~~bash
jmap -histo <pid>
~~~

Chỉ đếm object live:

~~~bash
jmap -histo:live <pid>
~~~

Trên JDK 24.0.2, histogram có thể ghi ra file:

~~~bash
jmap "-histo:live,file=heap-histogram.txt" <pid>
~~~

Output thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| `num` | Thứ tự dòng |
| `#instances` | Số instance của class |
| `#bytes` | Tổng shallow size của các instance |
| `class name` | Tên class hoặc tên mảng |

Histogram chỉ cung cấp thống kê theo class; nó không cho thấy toàn bộ đường tham chiếu giữa các object. Nếu histogram cho thấy một loại object bất thường, mở heap dump trong MAT để tìm GC roots và đường giữ tham chiếu.

## 7. Dùng jcmd GC.heap_dump làm lựa chọn hiện đại

Oracle khuyến nghị dùng `jcmd` thay cho `jmap` trong các quy trình chẩn đoán hiện đại vì `jmap` là công cụ experimental/unsupported và có thể không còn trong các JDK tương lai.

Kiểm tra cú pháp trên JVM đích:

~~~bash
jcmd <pid> help GC.heap_dump
~~~

Tạo HPROF live dump:

~~~bash
jcmd <pid> GC.heap_dump heap-live.hprof
~~~

Tạo dump gồm cả object unreachable:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

Tạo gzip-compressed HPROF:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap-live.hprof.gz
~~~

Khác biệt mặc định cần nhớ:

| Công cụ | Mặc định | Cách lấy toàn bộ object |
|---|---|---|
| `jmap -dump` | `all` nếu không ghi `live` hoặc `all` | Mặc định hoặc chỉ định `all` |
| `jcmd GC.heap_dump` | Chỉ live objects; yêu cầu full GC | Thêm `-all` |

Theo help của JDK 24, `GC.heap_dump` có Impact: High, phụ thuộc kích thước và nội dung heap. `-gz` nhận mức nén 1 đến 9; `-overwrite` cho phép ghi đè file có sẵn; `-parallel` điều chỉnh số thread dùng cho dump. Hãy kiểm tra help của đúng JVM trước khi dùng tùy chọn.

JDK 15 trở lên có thể tạo chunked gzip HPROF bằng `jcmd GC.heap_dump -gz=1`. Eclipse MAT phiên bản 1.12 trở lên hỗ trợ đọc định dạng chunked gzip này. Điều đó khác với file gzip HPROF thông thường do công cụ gzip của hệ điều hành tạo ra.

## 8. Ví dụ Java 17 hoàn chỉnh: tạo heap dump

Tạo file `src/demo/HeapDumpDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** A small process that retains objects for heap dump practice. */
public final class HeapDumpDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    /**
     * Retains four byte arrays and waits for inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the wait is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 4; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        System.out.println("READY retainedMiB=" + RETAINED.size());
        Thread.sleep(120_000);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d classes src/demo/HeapDumpDemo.java
~~~

Mở Terminal 1 và chạy:

~~~bash
java -Xms32m -Xmx128m -cp classes demo.HeapDumpDemo
~~~

Stdout chính xác:

~~~text
READY retainedMiB=4
~~~

Giữ tiến trình chạy. Mở Terminal 2, tìm PID:

~~~bash
jps -l
~~~

Tạo dump live bằng `jmap`:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

Tạo dump gzip:

~~~bash
jmap "-dump:live,format=b,gz=1,file=heap-live.hprof.gz" <pid>
~~~

Thay `<pid>` bằng PID thực tế của `demo.HeapDumpDemo`. Trên Windows PowerShell, đặt toàn bộ `-dump:...` trong dấu nháy kép để truyền nó như một đối số duy nhất cho `jmap`.

Có thể dùng `jcmd` thay thế:

~~~bash
jcmd <pid> GC.heap_dump heap-live-jcmd.hprof
~~~

Sau khi hoàn tất, quay lại Terminal 1 và nhấn Ctrl+C. File `.hprof` là bản dump để phân tích; file `.hprof.gz` là bản gzip-compressed.

## 9. Mở và phân tích HPROF bằng Eclipse MAT

Eclipse Memory Analyzer (MAT) đọc HPROF binary heap dump và cung cấp giao diện để phân tích object graph.

Quy trình cơ bản:

1. Mở MAT.
2. Chọn File → Open Heap Dump.
3. Chọn file `.hprof` hoặc file gzip HPROF được phiên bản MAT hỗ trợ.
4. Chờ MAT parse và index dump.
5. Xem Overview để nắm tổng dung lượng, class và số object.
6. Dùng Histogram để tìm class chiếm nhiều shallow heap.
7. Dùng Dominator Tree để tìm object hoặc nhóm object giữ nhiều retained heap.
8. Dùng Path to GC Roots để tìm vì sao object vẫn còn reachable.

Một số khái niệm quan trọng:

- **Shallow heap**: bộ nhớ trực tiếp do một object chiếm, không tính object được tham chiếu.
- **Retained heap**: lượng bộ nhớ có thể được giải phóng nếu object hoặc nhóm object đó không còn được giữ.
- **Dominator**: object chi phối khả năng reachability của các object khác trong graph.
- **GC roots**: các điểm bắt đầu mà GC dùng để xác định object còn sống.
- **Unreachable objects**: object không còn đường tham chiếu từ GC roots; chúng có thể chưa được thu gom tại thời điểm dump.

MAT có thể phân tích HPROF binary, nhưng kết quả còn phụ thuộc loại dump, JVM và cách tạo dump. Nếu cần xem object unreachable, hãy đảm bảo dump chứa chúng; dùng `jmap` với `all` hoặc `jcmd` với `-all` khi phù hợp.

## 10. Heap dump tự động khi OutOfMemoryError

Có thể cấu hình JVM tạo HPROF khi xảy ra `OutOfMemoryError`:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./heap-dumps \
  -jar application.jar
~~~

Thư mục đích cần tồn tại và có đủ dung lượng, đồng thời user chạy JVM phải có quyền ghi. Có thể chỉ định file cụ thể theo chính sách vận hành.

Cấu hình này hữu ích khi lỗi xảy ra ngoài giờ làm việc hoặc không thể attach kịp để tạo dump thủ công. Tuy nhiên, heap dump có thể lớn và việc ghi file cần thời gian, I/O và dung lượng lưu trữ đáng kể. Hãy kiểm tra dung lượng đĩa trước khi bật trong production.

HPROF agent cũ `-agentlib:hprof=heap=dump,format=b` đã bị loại bỏ từ Java 9. Không dùng lại hướng dẫn cũ yêu cầu HPROF agent trong các JDK hiện đại.

## 11. Rủi ro khi tạo và chia sẻ heap dump

Tạo heap dump có thể ảnh hưởng đáng kể đến ứng dụng:

- Dump lớn cần thời gian và I/O để ghi file.
- `jcmd GC.heap_dump` mặc định yêu cầu full GC; JVM có thể tạm dừng trong quá trình này.
- `jmap` có thể cần attach vào tiến trình và thực hiện thao tác heap inspection; thời gian phụ thuộc kích thước heap, collector và môi trường.
- Ghi file có thể làm đầy disk hoặc volume của container.
- File dump có thể chứa token, mật khẩu, thông tin cá nhân, nội dung request, dữ liệu cache và dữ liệu nghiệp vụ.
- Người có file HPROF có thể đọc được nhiều dữ liệu đang tồn tại trong heap.

Trước khi tạo dump trên production:

1. Xác định đúng PID và JVM.
2. Kiểm tra dung lượng trống, thư mục output và quyền ghi.
3. Chọn live/all theo mục tiêu điều tra.
4. Chọn gzip nếu cần giảm dung lượng lưu trữ hoặc truyền file.
5. Ghi lại thời điểm, JDK version, PID và lệnh đã chạy.
6. Hạn chế quyền truy cập file và thời gian lưu giữ.
7. Chỉ chuyển file qua kênh bảo mật đã được phê duyệt.

Không tải heap dump lên dịch vụ công cộng hoặc chia sẻ vào ticket/chat có nhiều người đọc khi chưa kiểm tra dữ liệu nhạy cảm và chính sách tổ chức.

## 12. Lỗi thường gặp và cách xử lý

### jmap không được nhận diện

`jmap` là công cụ JDK. Kiểm tra đang dùng JDK có thư mục `bin` chứa công cụ và `PATH` trỏ đến đúng JDK.

### More than one non-option argument

Shell có thể đã tách chuỗi `-dump:...` thành nhiều đối số. Truyền toàn bộ tùy chọn dump như một đối số duy nhất:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

### Unable to open socket file hoặc attach thất bại

Kiểm tra PID còn chạy, quyền user/group, attach mechanism, JDK của công cụ và JVM đích. Không dùng PID của một máy hoặc namespace khác.

### Không đủ dung lượng hoặc không ghi được file

Kiểm tra ổ đĩa, volume, quyền thư mục và đường dẫn mà tiến trình thực sự nhìn thấy. Chọn vị trí có đủ dung lượng và quyền ghi.

### File .hprof không mở được

Kiểm tra dump đã hoàn tất chưa, file có kích thước hợp lý không, file có thực sự là HPROF binary không và MAT có hỗ trợ phiên bản/biến thể đó không. HPROF gzip cần được mở bằng phiên bản MAT hỗ trợ gzip tương ứng.

### File gzip không mở được

Kiểm tra file có phải gzip thật hay chỉ đổi tên. Gzip thường bắt đầu bằng magic bytes `1F 8B`. Dùng `gzip -t` để kiểm tra tính toàn vẹn của luồng nén.

### MAT báo thiếu hoặc không thấy object unreachable

Kiểm tra dump được tạo bằng `live` hay `all`. Nếu chỉ dump live, object unreachable đã bị loại khỏi file. Tạo lại dump với `jmap` `all` hoặc `jcmd` `-all` nếu câu hỏi điều tra yêu cầu.

### Dump quá lớn hoặc phân tích quá chậm

Thử gzip, bảo đảm máy phân tích có đủ RAM và disk, hoặc dùng histogram trước để xác định class đáng chú ý. Đừng giảm dữ liệu cần thiết bằng `live` nếu đang cần phân tích object unreachable.

## 13. Checklist trước khi tạo và phân tích dump

- [ ] Xác nhận mục tiêu là Java heap dump HPROF hay OS core dump.
- [ ] Kiểm tra `jmap -h` của JDK hiện tại để biết đúng tùy chọn.
- [ ] Chọn `live` hoặc `all` theo câu hỏi cần trả lời.
- [ ] Ghi `format=b` để tạo HPROF binary.
- [ ] Chọn file output có đủ dung lượng và quyền ghi.
- [ ] Cân nhắc `gz` để giảm dung lượng.
- [ ] Nhớ mặc định `jmap` và `jcmd GC.heap_dump` khác nhau.
- [ ] Kiểm tra file đã ghi xong và header HPROF/gzip hợp lệ.
- [ ] Dùng MAT hoặc công cụ tương thích để phân tích.
- [ ] Bảo vệ file vì dump có thể chứa dữ liệu nhạy cảm.
- [ ] Ghi nhận PID, thời gian, JDK version, loại dump và command.
- [ ] Ưu tiên xem `jcmd GC.heap_dump` trên JDK hiện đại; `jmap` là công cụ experimental/unsupported.

## 14. Core dump và jhsdb jmap

Nếu cần phân tích OS core file, dùng Serviceability Agent thay vì đưa core file vào cú pháp PID của `jmap`:

~~~bash
jhsdb jmap --core ./core.1234 --exe ./java
~~~

Cặp `--core` và `--exe` phải được chỉ định cùng nhau. Với JVM đang chạy, `jhsdb jmap --pid <pid>` có thể thực hiện các thao tác mà công cụ hỗ trợ, nhưng Serviceability Agent có thể làm JVM bị dừng trong lúc attach; chỉ dùng khi đã hiểu tác động và có quyền phù hợp.

Trợ giúp:

~~~bash
jhsdb jmap --help
~~~

Một số tùy chọn liên quan dump:

- `--binaryheap`: dump Java heap ở định dạng HPROF.
- `--dumpfile <name>`: tên file output.
- `--gz <1-9>`: mức nén gzip.
- `--core` và `--exe`: chỉ định core file cùng executable tương ứng.

## 15. Tài liệu tham khảo

- [Oracle JDK 17 — The jmap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): cú pháp `-dump`, `live`, `format=b`, `file` và trạng thái unsupported của `jmap`.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): tùy chọn `GC.heap_dump`, `-all`, `-gz`, `-overwrite` và mức ảnh hưởng.
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): hướng dẫn chẩn đoán JVM và khuyến nghị dùng `jcmd` cho quy trình hiện đại.
- [Eclipse MAT — Acquiring Heap Dumps](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/acquiringheapdump.html): cách tạo và mở HPROF, gzip và hỗ trợ chunked gzip.
- [OpenJDK — HPROF heap dump implementation](https://github.com/openjdk/jdk11u/blob/master/src/hotspot/share/services/heapDumper.cpp): mô tả header, record và heap dump segment của HPROF.

`jmap -dump:...,format=b,file=...` tạo heap dump HPROF nhị phân để phân tích Java heap. Hiểu header/record của HPROF, phân biệt live với all, chọn gzip phù hợp và mở file bằng công cụ tương thích sẽ giúp việc điều tra memory leak chính xác hơn. Với JDK hiện đại, hãy cân nhắc `jcmd GC.heap_dump` và luôn bảo vệ dump như dữ liệu nhạy cảm.
