# Quản lý kết quả trung gian và kiểm tra tính đầy đủ

Trong thuật toán **ngoài bộ nhớ (external-memory algorithms)**, khối dữ liệu có thể lớn hơn RAM nhiều lần. Một phép sắp xếp, ghép dữ liệu, dựng chỉ mục, phân vùng hoặc tổng hợp thường không hoàn thành trong một lần xử lý liên tục; nó tạo ra hàng loạt **kết quả trung gian** nằm trên đĩa: những run đã sắp, các bucket, các file tạm, bảng băm phân vùng, checkpoint và manifest. Lỗi nghiêm trọng nhất đôi khi không phải thuật toán tính sai giá trị, mà là **chương trình công bố đã hoàn tất dù còn thiếu file, thiếu bản ghi, bản sao không nhất quán hoặc một lần ghi bị ngắt giữa chừng**.

Bài **“Quản lý kết quả trung gian và kiểm tra tính đầy đủ”** thuộc nhóm **Ngoài bộ nhớ** của Computer Science Algorithms. Bài dạy thiết kế vòng đời một kết quả trung gian; cách đặt tên, ghi tạm, commit; cách lưu **manifest** chứa nguồn gốc, số bản ghi và dấu vân tay; cách so sánh số lượng đầu vào/đầu ra; cách kiểm tra bất biến của mỗi giai đoạn; các chiến lược checkpoint, phục hồi khi crash, và cách đánh giá những gì thực sự được bảo đảm. Ví dụ xuyên suốt là **external merge sort**: chia dữ liệu thành nhiều run nhỏ đã sắp rồi k-way merge bằng hàng đợi ưu tiên.

Bài có chương trình **Java 17+ tự chứa**, chạy thật với dữ liệu trên đĩa tạm, mỗi run có số bản ghi và **SHA-256**, manifest được công bố qua đổi tên nguyên tử, kết quả cuối có **DONE marker** và readback để xác nhận. Bộ test gồm **364 dãy vét cạn**, **250 dãy có seed**, một dãy **10.000 bản ghi**, và fault injection sửa file trung gian, sửa dữ liệu nguồn, vượt giới hạn fan-in, tạo input sai. Các oracle exact lưu toàn bộ dữ liệu **chỉ trong test**, không làm thay đổi nguyên tắc giới hạn bộ nhớ của pipeline chính.

## 1. Vì sao phải quản lý kết quả trung gian?

Xét việc sắp xếp N=10 tỷ bản ghi khi máy chỉ đủ RAM giữ vài triệu bản ghi. Ta không thể đọc hết và sort trực tiếp trong bộ nhớ. Thay vào đó:

~~~text
Nguồn lớn trên đĩa
      |
      v
Đọc từng buffer vừa RAM
      |
      v
Sắp từng buffer và ghi run
      |
      v
Danh sách run-000000, run-000001, ...
      |
      v
K-way merge hoặc merge nhiều lượt
      |
      v
Tập dữ liệu đã sắp hoàn chỉnh
~~~

Những run là **kết quả trung gian**. Chúng không phải output cuối nhưng cũng không thể coi là rác: nếu mất một run, lần merge sau sẽ mất một phần dữ liệu. Nếu lặp lại một run hai lần, đầu ra sẽ bị nhân đôi một nhóm bản ghi.

Một hệ thống chỉ kiểm tra “file cuối có tồn tại” rất dễ báo thành công sai. Thiết kế tốt phải mô tả rõ **trạng thái từng giai đoạn** và điều kiện để chuyển sang giai đoạn kế tiếp.

## 2. Phân biệt tính hợp lệ, tính toàn vẹn và tính đầy đủ

Ba câu hỏi khác nhau:

1. **Hợp lệ (validity):** mỗi bản ghi có đúng schema, mỗi run có thứ tự đúng, phép merge có giữ tiêu chí sort hay không?
2. **Toàn vẹn nội dung (integrity):** byte file hiện tại có khớp với bản đã công bố trước đó hay không? Một checksum/hash hỗ trợ phát hiện thay đổi.
3. **Đầy đủ (completeness):** tất cả đầu vào dự kiến đã được xử lý đúng một lần và đầu ra không thiếu/không thừa bản ghi hay phân vùng nào?

Ví dụ file A và file B cùng có 100 dòng nhưng B bỏ dòng thứ 7 và nhân đôi dòng thứ 8. **Count bằng nhau, completeness sai**. B có thể vẫn đã sắp theo thứ tự, nên kiểm tra sortedness cũng chưa đủ.

Một dấu SHA-256 ghi sau khi tạo B sẽ mô tả B rất chính xác, nhưng tự nó **không biết** B có phải kết quả đúng từ A hay không. Vì thế cần **kết hợp provenance, count, hash, bất biến toán học và kiểm thử độc lập**.

## 3. Bất biến kế toán dữ liệu theo mỗi stage

Giả sử đầu vào có N bản ghi và stage chia thành r run. Nếu mọi bản ghi thuộc đúng một run thì:

~~~text
N_source = sum_(i=1)^r N_run_i.
~~~

Sau một phép merge không lọc và không gộp bản ghi:

~~~text
N_output = sum_(i=1)^r N_run_i.
~~~

Do đó một điều kiện cần là:

~~~text
N_source = sum(N_run_i) = N_output.
~~~

Đây là **cận kiểm tra cần thiết, không đủ** để chứng minh output chứa đúng mọi bản ghi. Kèm theo đó phải biết mỗi run có dữ liệu đúng, được merge đúng một lần và không thay đổi âm thầm sau kiểm tra.

Với stage được thiết kế để **lọc** hoặc **khử trùng lặp**, công thức thay đổi. Ví dụ:

~~~text
N_input = N_output + N_filtered + N_rejected.
~~~

Nếu kết quả sau join có thể nhân số lượng dòng, không được dùng đẳng thức N_input=N_output. Phải viết **phương trình kế toán phù hợp ngữ nghĩa stage**, tránh áp một quy tắc chung sai.

## 4. Manifest là hợp đồng của giai đoạn

**Manifest** là file metadata liệt kê những artifact thuộc một kết quả đã commit. Ví dụ run manifest dạng văn bản:

~~~text
RUNS_V1
SOURCE 7 <source-sha256>
RUN run-000000.dat 3 <run0-sha256>
RUN run-000001.dat 3 <run1-sha256>
RUN run-000002.dat 1 <run2-sha256>
END 7 3
~~~

Trong chương trình, các trường được phân tách bằng tab. Mỗi run lưu:

- **Tên file:** cùng quy ước, không chứa đường dẫn tùy ý.
- **Số bản ghi:** để so với số hàng thực khi quét file.
- **SHA-256:** để xác nhận byte file lúc kiểm tra khớp với byte file đã commit.

Header của manifest còn chứa **tổng số dòng nguồn** và **hash của file nguồn**. Dòng END tái khẳng định tổng bản ghi và số run. Nếu một run không được liệt kê, không được coi là một phần của stage đã commit.

Manifest phải đủ để **khôi phục danh sách artifact mà không quét đoán tên mọi file còn sót trong thư mục**. Một file `run-000123.dat.partial` tồn tại do crash không tự động trở thành run hợp lệ.

## 5. Định danh bản ghi để giữ được nguồn gốc

Mỗi dòng nguồn trong ví dụ chứa một số nguyên long là **sort key**. Khi đọc, chương trình gắn thêm **position** là số thứ tự dòng ban đầu:

~~~text
Input keys: 9,1,5,5,-3,12,1.

Rows:
(9,0), (1,1), (5,2), (5,3),
(-3,4), (12,5), (1,6).
~~~

Mỗi `Row(key, position)` là một bản ghi riêng, kể cả khi key trùng. Chính sách sort:

~~~text
Sắp tăng theo key.
Nếu key bằng nhau, sắp tăng theo position.
~~~

Quy tắc này tạo **thứ tự toàn phần** và giữ tính ổn định theo vị trí gốc của các key bằng nhau. Không được biến List bản ghi thành Set theo key rồi đánh mất những bản sao cùng giá trị.

Trong một pipeline thực, có thể dùng `(source-file-id, offset)` hoặc `(partition-id, ordinal)` để làm định danh ổn định. Cần có chính sách khi nguồn được đọc lại hoặc retry, để cùng một bản ghi không bị gắn ID khác và âm thầm đưa vào hai lần.

## 6. Đọc nguồn theo buffer, không tải hết lên RAM

Mô hình bên ngoài bộ nhớ cho phép RAM chứa B_rec bản ghi ở một thời điểm, trong khi tổng N lớn hơn B_rec nhiều lần. Ta đọc tuần tự từng dòng, gắn `position`, thêm vào buffer; đủ B_rec bản ghi thì sort và **flush** thành một run.

~~~text
buffer = []
for each input row:
    buffer.add(Row(key,ordinal++))
    if buffer.size == bufferCapacity:
        sort(buffer)
        flushOneRun(buffer)
        buffer.clear()

if buffer not empty:
    sort(buffer)
    flushOneRun(buffer)
~~~

Bộ nhớ buffer là O(B_rec). Sau khi ghi, buffer được tái sử dụng; chương trình không cần nhớ nội dung của mọi run, chỉ cần metadata tên/count/hash. Dù thế **metadata có r=ceil(N/B_rec) phần tử**, nên vẫn cần O(r) bộ nhớ cho danh sách run.

Bản Java dùng `BufferedReader` và `BufferedWriter` UTF-8; nó không đọc tất cả các dòng nguồn bằng `readAllLines`. Các bộ test mới giữ toàn bộ dãy để có oracle exact.

## 7. Tạo run đúng và theo thứ tự

Mỗi run là một file văn bản gồm các dòng:

~~~text
key<TAB>position
~~~

Quy trình flush:

1. Sort buffer bằng comparator `(key,position)` tăng dần.
2. Ghi từng Row ra file `run-xxxxxx.dat.partial`.
3. Đóng writer, để toàn bộ dữ liệu đã truyền qua API ghi hoàn tất.
4. Đổi tên file pending sang `run-xxxxxx.dat`.
5. Tính SHA-256 file đã commit và ghi số bản ghi vào metadata.

Từng run được **sắp đúng độc lập**. Sau này, k-way merge dựa vào giả thiết mỗi luồng đầu vào đã có thứ tự. Nếu một run bị mất tính sortedness, heap merge không còn chứng minh được output đã sort.

Không dùng một file vừa đang ghi dở làm input của stage sau. Tên `.partial` chính là cách nhắc hệ thống: “artifact này chưa thể dùng”.

## 8. Ghi file và công bố stage phải tách biệt

Việc tạo đủ r run file **không tự chứng minh** tất cả đã thành công. Ta cần một điểm **commit** rõ ràng cho cả stage.

Trong chương trình:

~~~text
run-000000.dat.partial -> run-000000.dat
run-000001.dat.partial -> run-000001.dat
...
runs.manifest.partial -> runs.manifest
~~~

Manifest chỉ được công bố **sau khi tất cả các run có tên chính thức, hash và count đã biết**. Điều này tạo quy ước:

~~~text
Không có runs.manifest hợp lệ
    => stage RUNS chưa được commit.
Có runs.manifest hợp lệ
    => phải kiểm tra tất cả artifact được liệt kê.
~~~

`Files.move(..., ATOMIC_MOVE)` yêu cầu filesystem hỗ trợ rename nguyên tử **trong cùng vùng lưu trữ**. Chương trình **fail fast** nếu không hỗ trợ, không âm thầm đổi sang rename không nguyên tử rồi tuyên bố crash-safe.

Đổi tên nguyên tử giúp người đọc không thấy một file đang được thay thế nửa chừng; tuy nhiên **không tự bảo đảm durable sau khi mất điện**. Hệ thống production còn cần chính sách `fsync`/force dữ liệu và metadata thư mục, kiểm tra hệ thống file, quyền truy cập và tính nhất quán khi nhiều writer.

## 9. Kiểm tra một manifest đã được tải lại

Sau khi tạo manifest, chương trình có thể giải phóng bộ nhớ hoặc khởi động lại tiến trình. Một bước resume phải **đọc manifest đã lưu** chứ không chỉ dựa vào object đang còn trong RAM.

Khi `loadRuns`:

- Header phải có đúng phiên bản.
- SOURCE phải có tổng số bản ghi hợp lệ.
- Mỗi RUN phải có tên đúng định dạng, count dương và hash.
- Không chấp nhận tên run bị lặp.
- Kiểm tra tổng các count không tràn long.
- Dòng END phải khớp tổng và số run.
- Với input rỗng, danh sách run rỗng và tổng bằng 0 là hợp lệ.

Ví dụ `runs.manifest` còn tồn tại nhưng một dòng RUN bị xóa; nếu END không khớp, loader phải dừng. Nếu file manifest đầy đủ nhưng một run bị mất hoặc hỏng, bước verify file thực tế phải phát hiện tiếp.

**Khác biệt giữa parse và verify:** parse chứng minh metadata **có hình dạng hợp lệ**; verify đọc file thật để biết metadata **có khớp artifact hay không**.

## 10. Kiểm tra nguồn trước khi khôi phục

Một pipeline có thể bị lỗi dù mọi run còn nguyên nếu **nguồn đã thay đổi** sau khi checkpoint. Ví dụ ETL chạy trên file nguồn bị cập nhật giữa hai lần thực thi; việc ghép run cũ với nguồn mới sẽ tạo dữ liệu không cùng phiên bản.

Bản Java kiểm tra:

~~~text
sha256(source_now) == manifest.sourceHash.
number_of_lines(source_now) == manifest.sourceCount.
~~~

Nếu hash hoặc số dòng không khớp, từ chối resume. Điều này đòi **nguồn được coi là bất biến sau checkpoint**.

Lưu ý: tính hash sau khi quét nguồn và kiểm tra lại **không tự tạo một snapshot nguyên tử** nếu một writer khác vẫn đang chỉnh nguồn đồng thời. Để có bảo đảm nhất quán mạnh trong production, cần snapshot version, file nguồn immutable, khóa ghi hoặc nguồn có generation ID và phiên bản dữ liệu rõ ràng.

## 11. Kiểm tra từng run trước khi merge

Với mỗi RunMeta đã load:

~~~text
1. File phải tồn tại.
2. SHA-256 file thực tế = hash khai báo.
3. Đọc và parse từng dòng theo schema key<TAB>position.
4. Tất cả row phải theo thứ tự (key,position) không giảm.
5. position thuộc [0,N_source).
6. Số row thực tế = count khai báo.
~~~

Khi phát hiện một trong các lỗi trên, từ chối merge. Không sửa file trung gian bằng phỏng đoán, không giảm count manifest để “cho vừa”, không bỏ qua file lỗi rồi tiếp tục như thể dữ liệu đầy đủ.

Mẫu kiểm tra này áp dụng rộng hơn sort: một bucket join có thể cần count, key-range, partition-id, min/max key; một aggregate cần tổng count đầu vào, số nhóm và phạm vi hỗ trợ; một chỉ mục cần số key, số page và bất biến liên kết giữa node.

## 12. Cộng tổng các run: điều kiện cần cho completeness

Cho n là tổng record input và n_i của các run:

~~~text
assert sum_i n_i == n
~~~

Chương trình **đọc lại count thực tế** của từng run rồi cộng để so với sourceCount. Đây là một kiểm tra mạnh hơn việc chỉ tin vào số count đã lưu trong manifest.

Nếu một run bị cắt ngắn nhưng manifest vẫn giữ count cũ, readback phát hiện. Nếu file bị chỉnh nhưng giữ nguyên số dòng, SHA-256 phát hiện thay đổi byte khi manifest ban đầu vẫn được tin cậy.

Tuy vậy, cả `sum count` và hash đều cần một **điểm tham chiếu tin cậy**: hash của file sai nhưng được ghi vào manifest như thể đúng không tự chứng minh sự tương đương ngữ nghĩa với nguồn. Chính vì vậy pipeline phải định nghĩa và bảo toàn cách **ánh xạ từng dòng nguồn sang run**.

## 13. K-way merge là tiêu thụ từng run chính xác một lần

Khi r run đã sắp và r nằm trong giới hạn số file có thể mở, ta mở một **Cursor** trên mỗi run và đưa bản ghi đầu vào `PriorityQueue` theo comparator `(key,position)`.

~~~text
for each run:
    cursor = open(run)
    if cursor.hasNext:
        heap.add(cursor)

while heap not empty:
    c = heap.removeMin()
    write(c.current)
    if c.advance():
        heap.add(c)
~~~

Bất biến: mỗi cursor chứa **bản ghi chưa xuất tiếp theo** của run đó. Bản ghi nhỏ nhất toàn cục trong những bản ghi chưa xuất chính là minimum của các đầu run, do mỗi run đã sorted.

Sau mỗi lần lấy một cursor, chương trình ghi đúng **một** bản ghi của cursor ấy, rồi chỉ đọc **bản ghi kế tiếp từ chính run đó**. Bởi thế không có lý do để đọc lại bản ghi cũ hay bỏ qua một bản ghi nào nếu cursor và vòng lặp hoạt động đúng.

Bộ đếm `consumed` của mỗi cursor được đối chiếu với count manifest ngay tại EOF và khi đọc quá count; mọi sai lệch đều là lỗi. Đây là phép kiểm tra vận hành, không chỉ là báo cáo kích thước.

## 14. Bất biến chứng minh output đã sắp

Trước mỗi vòng lặp, heap chứa phần tử nhỏ nhất chưa xuất của mỗi run còn dữ liệu. Gọi m là phần tử nhỏ nhất trong heap. Với mọi run, mọi phần tử chưa xuất đều không nhỏ hơn phần tử đầu đang nằm trong heap (vì run đã sorted). Vì m không lớn hơn mọi đầu run, m **không lớn hơn bất cứ phần tử chưa xuất nào** trên tất cả run.

Xuất m giữ thứ tự output không giảm. Sau khi advance cursor nguồn của m, heap tiếp tục đại diện đúng các đầu run. Quy nạp tới khi heap rỗng, toàn bộ output đã được sắp.

Comparator dùng **key trước, position sau**, bảo đảm hai bản ghi có key bằng nhau vẫn có thứ tự ổn định theo input gốc. Đây là kết quả quan trọng của cách gắn định danh cho record từ đầu pipeline.

## 15. Output không được xem là xong chỉ vì có file

Lần merge tạo:

~~~text
sorted.dat.partial
~~~

Chỉ sau khi viết xong, đóng writer và kiểm tra tổng số record bằng sourceCount, chương trình mới đổi tên thành:

~~~text
sorted.dat
~~~

Sau đó tính SHA-256 file kết quả và ghi một marker cuối:

~~~text
done.manifest.partial
  -> done.manifest
~~~

Marker DONE trong demo chứa:

~~~text
DONE_V1 <output-count> <sha256(sorted.dat)>
~~~

Khi khôi phục hoặc khi một process khác muốn tiêu thụ output, phải kiểm tra **có DONE marker hợp lệ**, số bản ghi trong DONE trùng sourceCount, SHA-256 file output trùng marker, số dòng thực tế trùng count và output đã sắp theo comparator.

Nếu mới có `sorted.dat` nhưng **chưa có DONE**, quy trình chưa được xác nhận hoàn thành. Điều này xử lý crash ở khoảng giữa đổi tên output và công bố kết quả.

## 16. Kiểm tra nội dung đã ghi: readback độc lập

Không nên giả định lời gọi ghi thành công đồng nghĩa nội dung đã bền vững và đúng. Một bước readback tốt kiểm tra **đúng đối tượng đã ghi**:

~~~text
Output file thật:
  - SHA-256 khớp DONE?
  - Số dòng khớp?
  - Format mỗi dòng hợp lệ?
  - Thứ tự mỗi cặp bản ghi hợp lệ?
  - Tổng khớp run manifest?
~~~

Trong ví dụ, `verifyDone` đọc lại file kết quả và đối chiếu những điều kiện đó. Việc đọc lại giúp phát hiện lỗi ở giữa stage hoặc file bị thay đổi sau khi ghi.

Trong ứng dụng chịu lỗi cao, cần lưu kết quả verify kèm `jobId`, `sourceVersion`, code version và timestamp, sau đó kiểm chứng lại khi artifact được sử dụng lâu về sau. Không nên xem một lần verify như giấy phép bất biến mãi mãi nếu người khác vẫn có quyền sửa file.

## 17. Vì sao chỉ có tổng số dòng vẫn thiếu?

Giả sử input là ba bản ghi phân biệt:

~~~text
A, B, C.
~~~

Một output sai có thể là:

~~~text
A, B, B.
~~~

Cả hai có count=3. Nếu thứ tự sort không phân biệt B/C theo key (ví dụ key đều bằng 5), output còn có thể qua kiểm tra sort. Vì thế cần bổ sung một trong những cách xác minh mạnh hơn:

- Theo dõi **ID nguồn duy nhất** và chứng minh mỗi ID đi qua stage đúng một lần.
- Với tập kiểm thử vừa RAM, sort full input/output bằng oracle độc lập rồi so **toàn bộ multiset**.
- Với input thực lớn, làm **đối soát ngoài bộ nhớ**: sort thêm theo ID, so từng dòng ID với chuỗi ID nguồn, hoặc external join output với ledger nguồn để kiểm tra đúng một lần.
- Dùng checksum/hàm fingerprint giao hoán làm tín hiệu phát hiện sai lệch, nhưng không nhầm chúng với bằng chứng tuyệt đối nếu có collision.

Chương trình kiểm thử thật sự so từng `Row(key,position)` đầu ra với một bản `List<Row>` exact sorted trong bộ test. Nhưng thuật toán production của demo không giữ toàn bộ input trong RAM để làm oracle; tính đầy đủ dựa trên sự đúng đắn của code tạo run và code merge, kết hợp manifest/readback và tính bất biến của nguồn.

## 18. SHA-256 xác nhận những gì và không xác nhận những gì?

SHA-256 của một file giúp nhận ra thay đổi byte với xác suất va chạm cực nhỏ khi ta có **digest gốc tin cậy**. Nó hữu ích khi file có cùng số dòng nhưng giá trị bên trong bị sửa, khi đường truyền hoặc đĩa bị lỗi, hoặc khi một artifact được sao chép qua nơi khác.

Nhưng cần giới hạn tuyên bố:

- SHA-256 của file output **không chứng minh output là kết quả đúng của thuật toán**.
- SHA-256 được tính lại từ **chính file đã hỏng** rồi cập nhật manifest theo thì cả hai vẫn “khớp”.
- Nếu đối thủ có quyền chỉnh cả artifact lẫn manifest, hash không có khóa **không phải chữ ký xác thực**; cần cơ chế tin cậy như chữ ký, HMAC hoặc kho metadata kiểm soát quyền.
- Hash và count không thay thế kiểm tra schema, sortedness, partition invariants hoặc tính bảo toàn dòng.
- Kiểm tra digest trước khi merge mà một writer khác vẫn có quyền sửa file sau đó tồn tại rủi ro **TOCTOU**; cần khóa/snapshot/immutable object để bảo đảm read đúng bản đã verify.

Vì vậy manifest và SHA-256 là **một lớp kiểm tra**, không phải toàn bộ chứng minh completeness.

## 19. Test tính đầy đủ bằng oracle khác với production

Khi n nhỏ, một oracle đơn giản có thể lưu tất cả Row vào RAM, sort bằng comparator rồi so từng phần tử với output:

~~~text
oracle = originalRows.clone()
oracle.sort(by key, then by position)

assert actualOutput.equals(oracle)
~~~

Điều này phát hiện **thiếu, trùng, sai key, sai ID hoặc sai thứ tự**. Nó độc lập với cách external merge chia run và cách heap hoạt động.

Nhưng nếu n là hàng tỷ, oracle full RAM không còn phù hợp mục tiêu ngoài bộ nhớ. Khi ấy dùng chứng minh theo stage, ledger theo ID, đối chiếu bằng external sort/join riêng, hoặc kiểm toán theo partition. **Tách rõ code test** và **code đường dữ liệu chính** giúp tránh nhầm lẫn “ví dụ có oracle” với “pipeline lúc chạy giữ toàn bộ dữ liệu”.

## 20. Fan-in và số file mở là tài nguyên hữu hạn

K-way merge trực tiếp cần giữ tối đa r con trỏ đang mở và một heap cỡ r. Nếu r lớn hơn giới hạn file descriptor, mỗi cursor buffer hoặc memory budget, không thể mở tất cả run cùng lúc.

Chương trình có tham số `maxFanIn`. Khi `runCount > maxFanIn`, nó **ném IOException và không tạo DONE**:

~~~text
fan-in exceeded: multi-pass required
~~~

Đây là hành vi đúng hơn so với lén bỏ một số run để “vừa RAM”, vì bỏ run sẽ khiến completeness thất bại.

Giải pháp production là **multi-pass merging**: chia r run thành nhóm tối đa F, merge từng nhóm thành run của lượt sau, commit **manifest cho mỗi lượt**, rồi tiếp tục cho tới khi còn một run hoặc số run không vượt F.

~~~text
Pass 0: 100 runs.
F=10.
Pass 1: 10 merged runs.
Pass 2: 1 final run.
~~~

Đối với mỗi pass, phải giữ invariant tổng record, hash và metadata của các run mới. Bản Java demo cố ý giới hạn một pass cuối, **không cài multi-pass**; nếu vượt fan-in thì từ chối rõ ràng.

## 21. Độ phức tạp tính toán và I/O

Gọi N là tổng số bản ghi, b là số bản ghi vừa trong buffer, r=ceil(N/b) (với N=0 thì r=0).

**Run generation**:

- Đọc N bản ghi tuần tự từ đĩa.
- Mỗi buffer sort tối đa b phần tử: tổng O(N log b) phép so sánh.
- Ghi N bản ghi thành r run.
- Bộ nhớ nội dung khoảng O(b), thêm O(r) metadata.

**K-way merge một lượt** khi r≤F:

- Đọc N bản ghi từ r run.
- Mỗi pop/push heap O(log max(1,r)); tổng O(N log max(2,r)) CPU.
- Ghi N bản ghi vào output.
- Cần O(r) cursor/heap và các buffer I/O.

**I/O theo khối:** nếu bộ nhớ trong có thể chứa M bản ghi và kích thước block là B bản ghi, external merge sort tối ưu nhiều pass có độ phức tạp I/O điển hình:

~~~text
O((N/B) * log_(M/B)(N/B))
~~~

với các giả thiết chuẩn M/B≥2 và N đủ lớn. Đây là **mô hình số lần truyền block**, khác với độ phức tạp CPU O(N log N) của sort thông thường.

Code demo dùng file văn bản và `BufferedReader`, kèm các lần verify hash/sortedness nên thực tế sẽ có **thêm lượt đọc**. Những lượt đó đổi throughput I/O để lấy khả năng phát hiện lỗi; cần tính vào ngân sách thời gian.

## 22. Disk space, memory và file lifecycle

Bài ngoài bộ nhớ có thể không thiếu RAM nhưng **hết đĩa tạm**:

~~~text
Source: xấp xỉ N records.
Runs đang tồn tại: xấp xỉ N records.
Output đang ghi: tối đa N records.
Pass trung gian mới: có thể thêm một bản sao N records.
~~~

Trước khi bắt đầu, nên ước lượng dung lượng tạm và dung lượng cao điểm. Không xóa run cũ trước khi run mới đã được commit và verify; nếu xóa sớm rồi crash, không thể phục hồi từ checkpoint cũ.

Tách **đường dữ liệu đang xây** (`.partial`) khỏi **dữ liệu đã commit** (`.dat`, manifest). Chỉ tiến hành garbage collection khi biết artifact không còn được manifest của stage đang sử dụng hoặc checkpoint phục hồi cần tới.

Trên máy nhiều job, tên thư mục nên có jobId và attemptId; quota và tự dọn theo TTL phải không xóa nhầm một job vẫn hoạt động.

## 23. Bảng tình huống crash và cách xử lý

| Điểm crash | Trạng thái có thể nhìn thấy | Cách xử lý an toàn |
| --- | --- | --- |
| Đang ghi một run | Chỉ có file `.partial` | Chưa tính vào stage; tạo lại từ nguồn/checkpoint |
| Đã ghi vài run, chưa có manifest | Có vài `.dat` nhưng không có danh sách commit | Không tự đoán đã đủ, kiểm tra/khởi tạo lại stage |
| Có manifest, mất một run | Manifest liệt kê file không tồn tại | Verify thất bại; phục hồi run hoặc dựng lại |
| Một run bị sửa nội dung | Count có thể không đổi | SHA-256 không khớp; reject |
| Nguồn đổi sau checkpoint | Hash nguồn không khớp | Reject; chọn nguồn version nhất quán |
| Đang merge | `sorted.dat.partial` | Không công bố output |
| Đã rename output, chưa có DONE | `sorted.dat` nhưng không có `done.manifest` | Coi chưa commit; verify/recover theo quy trình |
| Có DONE nhưng output bị sửa | DONE vẫn tồn tại | Verify checksum/count/sortedness từ chối |
| Số run vượt giới hạn F | Thiếu đủ tài nguyên mở file | Fail fast, lập kế hoạch multi-pass |

Đây là **bảng trạng thái logic**. Các chi tiết recover phụ thuộc hệ thống file, quyền truy cập, khả năng atomic rename, tính durable và cách giữ file nguồn.

## 24. Khôi phục và tính idempotent

Một tác vụ **idempotent** cho cùng một input version và cấu hình phải có khả năng chạy lại mà không làm dữ liệu xuất hiện hai lần. Kỹ thuật phổ biến:

1. Mỗi attempt viết vào **thư mục/tên artifact riêng**.
2. Trước khi dùng checkpoint, load và verify manifest đã commit.
3. Không đọc file partial như artifact hoàn chỉnh.
4. Không tự động append vào output đã hoàn thành.
5. Chỉ publish pointer/marker tới kết quả mới **sau khi verify**, và tránh hai writer cùng commit bằng khóa hoặc compare-and-swap phiên bản.
6. Khi retry, dùng **source snapshot/version** và cùng quy tắc đánh ID để không đổi nghĩa input.

Bản demo dùng thư mục tạm **mới** cho mỗi test/run, và `CREATE_NEW` để tránh ghi đè artifact cùng tên. Nó trình diễn checkpoint và readback, **không** tự động resume nửa chừng cùng thư mục, không có distributed locking hay compare-and-swap. Đó là giới hạn được công bố rõ, thay vì giả định mọi lỗi crash đều được phục hồi tự động.

## 25. Áp dụng ngoài external merge sort

**Hash join ngoài bộ nhớ:** sau partitioning, mỗi bucket của hai phía nên có manifest, số row, hash, partition key. Kết quả join không nhất thiết có count bằng tổng hai phía; completeness phải dựa trên số cặp khớp và bất biến partition.

**MapReduce/ETL:** từng mapper ghi shard với `attemptId`; reducer chỉ nhận những shard thuộc một danh sách commit thống nhất, tránh đọc cả output từ attempt thất bại và attempt retry.

**Dựng chỉ mục:** file page/segment được ghi riêng, rồi commit manifest trỏ đúng generation; chỉ khi các page và liên kết hợp lệ mới publish version chỉ mục.

**Aggregation:** đối soát số record đầu vào bằng tổng `countByGroup`, kiểm tra key-range/partition coverage, nhưng không dùng COUNT một mình để khẳng định mỗi giá trị tổng đúng.

**External graph algorithms:** frontier hoặc adjacency shard của mỗi vòng lặp cần checkpoint, tổng vertex/edge theo đúng quy tắc stage và cơ chế tránh lặp một vertex ngoài ý muốn.

Mẫu chung là **lập manifest cho một tập artifact thống nhất, viết bất biến của phép biến đổi, verify rồi mới publish**.

## 26. Security, đường dẫn và provenance

Một manifest lấy từ dữ liệu không tin cậy có thể chứa tên file như đường dẫn đi lên thư mục cha. Vì vậy loader demo chỉ chấp nhận tên run khớp định dạng nghiêm:

~~~text
run-[0-9]{6}.dat
~~~

và chặn tên trùng. Không cho manifest tự chọn đường dẫn tuyệt đối để đọc/xóa file tùy ý. Một hệ thống production còn cần kiểm tra symlink, realpath, quyền folder và ranh giới tenant.

Hash SHA-256 đủ giúp phát hiện lỗi thông thường nhưng **không thay thế xác thực nguồn**. Nếu dữ liệu đến từ nhiều tổ chức hoặc môi trường không tin cậy, cần metadata có nguồn xác thực, chữ ký/HMAC, ACL và audit log.

Provenance không chỉ là tên file: bao gồm input version, job/attempt ID, phiên bản code, cấu hình sort/merge, schema, số record và thời điểm commit. Thiếu provenance khiến một manifest hợp lệ về định dạng vẫn có thể bị dùng sai cho một lần chạy khác.

## 27. Ví dụ nhỏ: bảy số và ba run

Dữ liệu nguồn:

~~~text
9,1,5,5,-3,12,1
~~~

Buffer capacity = 3. Các run trước khi merge:

~~~text
Run 0 từ 9,1,5:
    (1,1),(5,2),(9,0).

Run 1 từ 5,-3,12:
    (-3,4),(5,3),(12,5).

Run 2 từ 1:
    (1,6).
~~~

Ở mỗi cặp `(key,position)`, position là thứ tự dòng nguồn bắt đầu từ 0. K-way merge theo `(key,position)` tạo:

~~~text
(-3,4),(1,1),(1,6),(5,2),
(5,3),(9,0),(12,5).
~~~

Khi chỉ in key, output là:

~~~text
[-3, 1, 1, 5, 5, 9, 12]
~~~

Có **7 bản ghi** đầu vào và **7 bản ghi** đầu ra; ba run đều được tiêu thụ hoàn toàn. Kiểm tra lại cặp position bảo đảm hai số 1 và hai số 5 không bị đánh tráo hoặc bỏ bớt một bản sao.

## 28. Mã Java 17+ hoàn chỉnh

Lưu mã dưới đây thành **ExternalRunCompleteness.java**. Mã không cần thư viện ngoài, dùng JDK 17 hoặc mới hơn. `Path`, `Files`, `BufferedReader`, `MessageDigest`, `HexFormat` và `PriorityQueue` đều có trong thư viện Java chuẩn.

**Những API quan trọng:**

- `writeInput`: tạo file nguồn thử nghiệm, một long mỗi dòng.
- `makeRuns`: chỉ giữ buffer giới hạn, sort, flush từng run, sau đó commit manifest stage.
- `loadRuns`: đọc một checkpoint từ đĩa và kiểm tra phiên bản, tên file, count, tổng count và uniqueness.
- `verifyRuns`: kiểm tra nguồn, từng run, checksum, row count, thứ tự sort và miền position.
- `merge`: mở tối đa `maxFanIn` run, dùng heap để merge, ghi output partial rồi commit cùng DONE marker.
- `verifyDone`: đọc lại marker và file cuối để đối chiếu SHA-256, tổng row và sortedness.
- `test` và `verify`: dùng oracle full sort **chỉ trong test** và fault injection.
- `cleanup`: xóa **thư mục tạm do chính chương trình tạo ra** sau khi thử nghiệm.

Bản demo yêu cầu filesystem hỗ trợ `ATOMIC_MOVE` cho các đường dẫn trong thư mục tạm. Nó không gọi `FileChannel.force` hoặc đồng bộ metadata thư mục và không hỗ trợ tự recovery khi crash; **atomic rename không đồng nghĩa với durability hoàn chỉnh khi mất điện**. Mô hình một lượt merge cũng giới hạn fan-in; dữ liệu cần nhiều pass sẽ bị từ chối để tránh kết quả thiếu.

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.stream.*;

public final class ExternalRunCompleteness {
    private ExternalRunCompleteness() {}
    public record Row(long key, long position) {}
    public record Run(String name, long count, String hash) {}
    public record Manifest(long sourceCount, String sourceHash,
                           List<Run> runs) {}
    public record Done(long count, String hash) {}
    private static final Comparator<Row> ORDER =
            Comparator.comparingLong(Row::key)
                      .thenComparingLong(Row::position);

    private static String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(path)) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) != -1)
                    digest.update(buffer, 0, n);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static void commit(Path pending, Path ready) throws IOException {
        Files.move(pending, ready, StandardCopyOption.ATOMIC_MOVE);
    }

    private static Row parseRow(String s) throws IOException {
        int t = s.indexOf('\t');
        if (t < 1 || t == s.length()-1 || s.indexOf('\t',t+1) >= 0)
            throw new IOException("bad intermediate row");
        try {
            return new Row(Long.parseLong(s.substring(0,t)),
                           Long.parseLong(s.substring(t+1)));
        } catch (NumberFormatException ex) {
            throw new IOException("bad intermediate number", ex);
        }
    }

    private static void writeRow(BufferedWriter writer, Row r)
            throws IOException {
        writer.write(r.key()+"\t"+r.position()+"\n");
    }

    private static long unsignedCount(String s) throws IOException {
        try {
            long v = Long.parseLong(s);
            if (v<0) throw new NumberFormatException("negative");
            return v;
        } catch (NumberFormatException ex) {
            throw new IOException("bad manifest count",ex);
        }
    }

    public static Path writeInput(Path dir, long[] keys)
            throws IOException {
        Path source=dir.resolve("source.txt");
        try (BufferedWriter writer=Files.newBufferedWriter(source,
                StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW)) {
            for(long value:keys) writer.write(value+"\n");
        }
        return source;
    }

    private static Run flushRun(Path dir, int index, List<Row> values)
            throws IOException {
        values.sort(ORDER);
        String name=String.format(Locale.ROOT,"run-%06d.dat",index);
        Path temp=dir.resolve(name+".partial");
        try(BufferedWriter writer=Files.newBufferedWriter(temp,
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW)){
            for(Row row:values)writeRow(writer,row);
        }
        Path ready=dir.resolve(name);
        commit(temp,ready);
        return new Run(name,values.size(),sha256(ready));
    }

    public static Manifest makeRuns(Path source, Path dir, int capacity)
            throws IOException {
        if (capacity<=0)throw new IllegalArgumentException("capacity <= 0");
        List<Row> buffer=new ArrayList<>(capacity);
        List<Run> runs=new ArrayList<>();
        long index=0;
        try(BufferedReader reader=Files.newBufferedReader(source,
                StandardCharsets.UTF_8)){
            String line;
            while((line=reader.readLine())!=null){
                long value;
                try{value=Long.parseLong(line);}
                catch(NumberFormatException ex){
                    throw new IOException("source is not a long",ex);
                }
                if(index==Long.MAX_VALUE)
                    throw new IOException("index overflow");
                buffer.add(new Row(value,index++));
                if(buffer.size()==capacity){
                    runs.add(flushRun(dir,runs.size(),buffer));
                    buffer.clear();
                }
            }
        }
        if(!buffer.isEmpty())runs.add(flushRun(dir,runs.size(),buffer));
        Manifest m=new Manifest(index,sha256(source),List.copyOf(runs));
        List<String> lines=new ArrayList<>();
        lines.add("RUNS_V1");
        lines.add("SOURCE\t"+m.sourceCount()+"\t"+m.sourceHash());
        for(Run r:m.runs())lines.add("RUN\t"+r.name()+"\t"
                                   +r.count()+"\t"+r.hash());
        lines.add("END\t"+m.sourceCount()+"\t"+m.runs().size());
        Path temp=dir.resolve("runs.manifest.partial");
        Files.write(temp,lines,StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);
        commit(temp,dir.resolve("runs.manifest"));
        return m;
    }

    public static Manifest loadRuns(Path dir) throws IOException {
        List<String> lines=Files.readAllLines(
                dir.resolve("runs.manifest"),StandardCharsets.UTF_8);
        if(lines.size()<3 || !lines.get(0).equals("RUNS_V1"))
            throw new IOException("bad run manifest");
        String[] source=lines.get(1).split("\t",-1);
        if(source.length!=3 || !source[0].equals("SOURCE"))
            throw new IOException("bad SOURCE header");
        long expected=unsignedCount(source[1]),sum=0;
        Set<String> names=new HashSet<>();
        List<Run> runs=new ArrayList<>();
        for(int i=2;i<lines.size()-1;i++){
            String[] f=lines.get(i).split("\t",-1);
            if(f.length!=4 || !f[0].equals("RUN")
                    || !f[1].matches("run-[0-9]{6}\\.dat")
                    || !names.add(f[1]))
                throw new IOException("bad run name/record");
            long count=unsignedCount(f[2]);
            if(count==0)throw new IOException("empty run");
            try{sum=Math.addExact(sum,count);}
            catch(ArithmeticException ex){
                throw new IOException("count overflow",ex);
            }
            runs.add(new Run(f[1],count,f[3]));
        }
        String[] end=lines.get(lines.size()-1).split("\t",-1);
        if(end.length!=3||!end[0].equals("END")
                ||unsignedCount(end[1])!=expected
                ||unsignedCount(end[2])!=runs.size()
                ||sum!=expected)
            throw new IOException("incomplete run manifest");
        return new Manifest(expected,source[2],List.copyOf(runs));
    }

    public static void verifyRuns(Path source, Path dir, Manifest manifest)
            throws IOException {
        if(!sha256(source).equals(manifest.sourceHash()))
            throw new IOException("source changed");
        long sourceLines=0;
        try(BufferedReader r=Files.newBufferedReader(
                source,StandardCharsets.UTF_8)){
            while(r.readLine()!=null)sourceLines++;
        }
        if(sourceLines!=manifest.sourceCount())
            throw new IOException("source line count mismatch");
        long sum=0;
        for(Run run:manifest.runs()){
            Path path=dir.resolve(run.name());
            if(!sha256(path).equals(run.hash()))
                throw new IOException("run hash mismatch");
            Row previous=null;
            long seen=0;
            try(BufferedReader r=Files.newBufferedReader(
                    path,StandardCharsets.UTF_8)){
                String line;
                while((line=r.readLine())!=null){
                    Row current=parseRow(line);
                    if(previous!=null&&ORDER.compare(previous,current)>0)
                        throw new IOException("run not sorted");
                    if(current.position()<0
                            ||current.position()>=manifest.sourceCount())
                        throw new IOException("position out of range");
                    previous=current;
                    seen++;
                }
            }
            if(seen!=run.count())throw new IOException("run count mismatch");
            sum+=seen;
        }
        if(sum!=manifest.sourceCount())
            throw new IOException("input/run totals differ");
    }

    private static final class Cursor implements AutoCloseable {
        final BufferedReader reader;
        final Run run;
        Row current,previous;
        long consumed;
        Cursor(Path path, Run run) throws IOException {
            this.reader=Files.newBufferedReader(path,StandardCharsets.UTF_8);
            this.run=run;
        }
        boolean next() throws IOException {
            String line=reader.readLine();
            if(line==null){
                if(consumed!=run.count())throw new IOException("short run");
                current=null;
                return false;
            }
            Row row=parseRow(line);
            if(previous!=null&&ORDER.compare(previous,row)>0)
                throw new IOException("run became unsorted");
            current=previous=row;
            consumed++;
            if(consumed>run.count())throw new IOException("extra run row");
            return true;
        }
        public void close() throws IOException {reader.close();}
    }

    public static Done merge(Path source, Path dir, int maxFanIn)
            throws IOException {
        if(maxFanIn<=0)throw new IllegalArgumentException("bad fan-in");
        Manifest manifest=loadRuns(dir);
        verifyRuns(source,dir,manifest);
        if(manifest.runs().size()>maxFanIn)
            throw new IOException("fan-in exceeded: multi-pass required");
        PriorityQueue<Cursor> heap=new PriorityQueue<>(
                Comparator.comparing((Cursor c)->c.current,ORDER));
        List<Cursor> opened=new ArrayList<>();
        Path partial=dir.resolve("sorted.dat.partial");
        long count=0;
        try{
            for(Run run:manifest.runs()){
                Cursor c=new Cursor(dir.resolve(run.name()),run);
                opened.add(c);
                if(c.next())heap.add(c);
            }
            try(BufferedWriter writer=Files.newBufferedWriter(partial,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW)){
                while(!heap.isEmpty()){
                    Cursor c=heap.remove();
                    writeRow(writer,c.current);
                    count++;
                    if(c.next())heap.add(c);
                }
            }
        }finally{
            for(Cursor c:opened)c.close();
        }
        if(count!=manifest.sourceCount())
            throw new IOException("merged row count mismatch");
        Path output=dir.resolve("sorted.dat");
        commit(partial,output);
        Done done=new Done(count,sha256(output));
        Path temp=dir.resolve("done.manifest.partial");
        Files.writeString(temp,"DONE_V1\t"+done.count()
                +"\t"+done.hash()+"\n",StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);
        commit(temp,dir.resolve("done.manifest"));
        return done;
    }

    public static Done verifyDone(Path dir) throws IOException {
        Manifest manifest=loadRuns(dir);
        List<String> lines=Files.readAllLines(
                dir.resolve("done.manifest"),StandardCharsets.UTF_8);
        if(lines.size()!=1)throw new IOException("bad DONE lines");
        String[] f=lines.get(0).split("\t",-1);
        if(f.length!=3||!f[0].equals("DONE_V1"))
            throw new IOException("bad DONE marker");
        Done done=new Done(unsignedCount(f[1]),f[2]);
        Path output=dir.resolve("sorted.dat");
        if(done.count()!=manifest.sourceCount()
                ||!sha256(output).equals(done.hash()))
            throw new IOException("final checksum/count mismatch");
        long n=0;
        Row previous=null;
        try(BufferedReader r=Files.newBufferedReader(
                output,StandardCharsets.UTF_8)){
            String line;
            while((line=r.readLine())!=null){
                Row current=parseRow(line);
                if(previous!=null&&ORDER.compare(previous,current)>0)
                    throw new IOException("output not sorted");
                previous=current;
                n++;
            }
        }
        if(n!=done.count())throw new IOException("output rows mismatch");
        return done;
    }

    private static List<Row> readOutput(Path path) throws IOException {
        List<Row> rows=new ArrayList<>();
        try(BufferedReader r=Files.newBufferedReader(
                path,StandardCharsets.UTF_8)){
            String line;
            while((line=r.readLine())!=null)rows.add(parseRow(line));
        }
        return rows;
    }

    private static void cleanup(Path dir) throws IOException {
        try(Stream<Path> paths=Files.walk(dir)){
            for(Path p:paths.sorted(Comparator.reverseOrder()).toList())
                Files.deleteIfExists(p);
        }
    }

    private static void test(long[] keys, int capacity)
            throws IOException {
        Path dir=Files.createTempDirectory("ext-run-test-");
        try{
            Path source=writeInput(dir,keys);
            Manifest made=makeRuns(source,dir,capacity);
            Manifest reloaded=loadRuns(dir);
            if(!made.equals(reloaded))
                throw new AssertionError("manifest load mismatch");
            verifyRuns(source,dir,reloaded);
            Done done=merge(source,dir,128);
            if(!done.equals(verifyDone(dir)))
                throw new AssertionError("DONE readback mismatch");
            List<Row> oracle=new ArrayList<>();
            for(int i=0;i<keys.length;i++)oracle.add(new Row(keys[i],i));
            oracle.sort(ORDER);
            if(!oracle.equals(readOutput(dir.resolve("sorted.dat"))))
                throw new AssertionError("independent multiset oracle failed");
        }finally{cleanup(dir);}
    }

    @FunctionalInterface
    private interface IOAction {void run() throws IOException;}

    private static void shouldReject(IOAction action) throws IOException {
        try{action.run();}
        catch(IOException expected){return;}
        throw new AssertionError("corruption was accepted");
    }

    private static void failureTests() throws IOException {
        {
            Path dir=Files.createTempDirectory("run-tamper-");
            try{
                Path source=writeInput(dir,new long[]{3,1,2,0,4});
                Manifest m=makeRuns(source,dir,2);
                Files.writeString(dir.resolve(m.runs().get(0).name()),
                        "99\t99\n",StandardCharsets.UTF_8,
                        StandardOpenOption.APPEND);
                shouldReject(()->verifyRuns(source,dir,m));
                shouldReject(()->verifyDone(dir));
            }finally{cleanup(dir);}
        }
        {
            Path dir=Files.createTempDirectory("source-tamper-");
            try{
                Path source=writeInput(dir,new long[]{3,2,1});
                Manifest m=makeRuns(source,dir,2);
                Files.writeString(source,"77\n",StandardCharsets.UTF_8,
                        StandardOpenOption.APPEND);
                shouldReject(()->verifyRuns(source,dir,m));
            }finally{cleanup(dir);}
        }
        {
            Path dir=Files.createTempDirectory("fanin-reject-");
            try{
                Path source=writeInput(dir,
                        new long[]{9,8,7,6,5,4,3,2,1});
                makeRuns(source,dir,2);
                shouldReject(()->merge(source,dir,3));
                if(Files.exists(dir.resolve("done.manifest")))
                    throw new AssertionError("invalid DONE commit");
            }finally{cleanup(dir);}
        }
        {
            Path dir=Files.createTempDirectory("invalid-source-");
            try{
                Path source=dir.resolve("source.txt");
                Files.writeString(source,"1\n\n2\n",StandardCharsets.UTF_8);
                shouldReject(()->makeRuns(source,dir,2));
            }finally{cleanup(dir);}
        }
        boolean rejected=false;
        try{makeRuns(Path.of("unused"),Path.of("unused"),0);}
        catch(IllegalArgumentException expected){rejected=true;}
        if(!rejected)throw new AssertionError("zero buffer accepted");
    }

    public static void verify() throws IOException {
        int exhaustive=0;
        for(int n=0;n<=5;n++){
            int cases=1;
            for(int i=0;i<n;i++)cases*=3;
            for(int mask=0;mask<cases;mask++){
                long[] keys=new long[n];
                int x=mask;
                for(int j=0;j<n;j++){keys[j]=x%3-1;x/=3;}
                test(keys,3);
                exhaustive++;
            }
        }
        Random rng=new Random(5202026L);
        int randomCases=0;
        for(int t=0;t<250;t++){
            int n=rng.nextInt(61);
            long[] keys=new long[n];
            for(int i=0;i<n;i++){
                keys[i]=switch(t%4){
                    case 0->rng.nextInt(13)-6;
                    case 1->rng.nextLong();
                    case 2->i%3==0?Long.MIN_VALUE:Long.MAX_VALUE;
                    default->n-i;
                };
            }
            test(keys,1+rng.nextInt(10));
            randomCases++;
        }
        long[] large=new long[10000];
        for(int i=0;i<large.length;i++)
            large[i]=(i*37L)%101-50;
        test(large,256);
        failureTests();
        System.out.println("Exhaustive ordered streams: "
                +exhaustive+" PASS");
        System.out.println("Seeded duplicate/extreme cases: "
                +randomCases+" PASS");
        System.out.println("External merge n=10000 buffer=256: PASS");
        System.out.println("Manifest tamper, missing DONE, fan-in and bad source: PASS");
    }

    public static void main(String[] args) throws IOException {
        Path dir=Files.createTempDirectory("ext-run-demo-");
        try{
            long[] keys={9,1,5,5,-3,12,1};
            Path source=writeInput(dir,keys);
            Manifest m=makeRuns(source,dir,3);
            Manifest loaded=loadRuns(dir);
            verifyRuns(source,dir,loaded);
            Done done=merge(source,dir,16);
            Done verified=verifyDone(dir);
            List<Long> sortedKeys=new ArrayList<>();
            for(Row row:readOutput(dir.resolve("sorted.dat")))
                sortedKeys.add(row.key());
            System.out.println("Input rows: "+m.sourceCount());
            System.out.println("Committed intermediate runs: "
                    +loaded.runs().size());
            System.out.println("Sorted keys: "+sortedKeys);
            System.out.println("Final count/hash verified: "
                    +done.equals(verified));
        }finally{cleanup(dir);}
        verify();
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac ExternalRunCompleteness.java
java ExternalRunCompleteness
~~~

**Stdout thực tế đã quan sát được khi chạy chương trình:**

~~~text
Input rows: 7
Committed intermediate runs: 3
Sorted keys: [-3, 1, 1, 5, 5, 9, 12]
Final count/hash verified: true
Exhaustive ordered streams: 364 PASS
Seeded duplicate/extreme cases: 250 PASS
External merge n=10000 buffer=256: PASS
Manifest tamper, missing DONE, fan-in and bad source: PASS
~~~

Lần chạy JShell để kiểm thử hiển thị một cảnh báo BOM ở phần khởi động shell, nhưng mã chương trình đã chạy và in đúng toàn bộ các dòng trên; các phép thử đều PASS.

## 29. Kiểm thử độc lập 364 dãy nhỏ

Chương trình sinh mọi dãy độ dài n từ 0 tới 5 trên bảng giá trị:

~~~text
{-1,0,1}
~~~

Có 3^n dãy độ dài n, tổng:

~~~text
1 + 3 + 9 + 27 + 81 + 243
    = 364.
~~~

Mỗi dãy được xử lý thật qua file nguồn, run files, manifest, readback, merge và DONE. Oracle độc lập:

1. Tạo danh sách `(key,originalPosition)` đầy đủ trong **bộ test**.
2. Sort danh sách bằng comparator `(key,position)`.
3. Đọc output `sorted.dat` từ đĩa.
4. So **toàn bộ List<Row>**: không thiếu, không thừa, không nhân đôi, không đảo vị trí record trùng key.

Bộ test còn xác nhận manifest sau khi load giống metadata vừa commit, mỗi run hợp lệ, marker DONE được đọc lại đúng. **364 dãy PASS**. Bao gồm input rỗng, chỉ một phần tử, giá trị trùng và trật tự nguồn bất kỳ.

## 30. Kiểm thử random 250 bộ và luồng 10.000 bản ghi

Với `Random(5202026L)`, bộ test sinh **250 dãy** dài từ 0 tới 60, luân phiên:

- Giá trị trong miền nhỏ nhiều trùng.
- Giá trị long ngẫu nhiên trên toàn miền 64-bit.
- Xen kẽ Long.MIN_VALUE và Long.MAX_VALUE.
- Dãy giảm theo index.

Dung lượng buffer được chọn từ 1 tới 10, tạo nhiều cấu hình số run và thứ tự merge khác nhau. Mỗi bộ vẫn so **toàn bộ output** với oracle exact. **250 bộ PASS**.

Bài stress n=10.000 với giá trị:

~~~text
key[i] = ((i*37) % 101) - 50.
Buffer capacity = 256.
~~~

Có nhiều key lặp, tổng 10.000 bản ghi, chia thành 40 run (39 run 256 bản ghi và run cuối 16 bản ghi). Với `maxFanIn=128`, chương trình merge trực tiếp và kiểm tra output exact; **PASS**.

Số run là 40 chứ không phải 39 vì ceil(10000/256)=40. Bộ test này có tính năng quan trọng: nhiều bản ghi key giống nhau nhưng position khác nhau, nên có thể xác minh ổn định theo thứ tự gốc.

## 31. Fault injection: cố tình gây lỗi phải bị phát hiện

Bên cạnh test “đầu vào tốt”, chương trình tạo các trường hợp lỗi:

1. **Append vào run sau khi manifest đã commit:** SHA-256 run không khớp; verify phải ném IOException.
2. **Thử đọc DONE chưa tồn tại:** khi stage chưa xuất ra kết quả, verifyDone phải thất bại; không thể công bố completed.
3. **Append dữ liệu vào file nguồn sau checkpoint:** hash nguồn khác, verifyStage từ chối.
4. **Run count vượt maxFanIn:** merge fail fast với IOException, và không sinh DONE marker.
5. **Nguồn có dòng trống không thể parse long:** tạo run phải từ chối, không gọi đó là stage hợp lệ.
6. **Buffer capacity bằng 0:** API ném IllegalArgumentException.

Đây là **fault injection có kiểm soát** trong các thư mục tạm do test tự tạo. Không sửa dữ liệu của người dùng hoặc file thật của repo. Kết quả chương trình ghi:

~~~text
Manifest tamper, missing DONE, fan-in and bad source: PASS
~~~

Những test này không thay thế mô phỏng crash ở mức hệ điều hành, hỏng page/sector hay storage distributed; chúng kiểm tra các bất biến có thể tạo tình huống lỗi từ trong Java.

## 32. Những lỗi triển khai phổ biến

1. **Coi file tạm tồn tại là hoàn thành**, dù writer chưa đóng hoặc chưa có commit.
2. **Không có manifest**, nên không biết một run bị thiếu hay là chưa từng tồn tại.
3. **Đưa file `.partial` vào danh sách merge** trước khi commit.
4. **Ghi manifest trước khi tất cả run sẵn sàng**, cho reader thấy stage chưa đủ.
5. **Chỉ so tổng count**, không phát hiện một dòng bị lặp và một dòng khác bị mất.
6. **Chỉ so hash output với hash vừa tự tính từ chính output**, không có metadata gốc đáng tin.
7. **Ghi hash run nhưng không verify trước khi đọc lại**.
8. **Tin count khai báo mà không đọc count thực tế** của file.
9. **Không kiểm tra run đã sorted**, khiến heap merge tạo output sai.
10. **Quên tie-break position**, mất tính stable khi key trùng.
11. **Gộp trùng key bằng Set**, mất bản ghi hợp lệ.
12. **Dùng Int count ở nơi tổng row có thể vượt 2^31**, gây overflow.
13. **Dùng phép trừ key1-key2 làm comparator long**, gây overflow.
14. **Mở tất cả run không giới hạn**, vượt số file handle hoặc RAM.
15. **Im lặng bỏ run khi không mở nổi file**, vi phạm completeness.
16. **Xóa run đầu vào trước khi output mới commit**, khiến crash không có cách resume.
17. **Xóa artifact từ một checkpoint còn được tham chiếu**, phá khả năng phục hồi.
18. **Cho rằng ATOMIC_MOVE tự đồng bộ mọi dữ liệu xuống đĩa**, nhầm atomicity với durability.
19. **Cho rằng manifest có hash là đã chống mọi thay đổi độc hại**, dù cả manifest có thể bị sửa.
20. **Dùng đường dẫn file từ manifest tùy ý**, tạo nguy cơ path traversal.
21. **Trộn run từ hai input version** khác nhau mà không kiểm tra provenance.
22. **Tự động append vào output khi retry**, dẫn tới record trùng.
23. **Công bố DONE trước khi tính và kiểm tra output count**, báo thành công quá sớm.
24. **Không xử lý input rỗng**, dù một output rỗng hợp lệ vẫn phải có DONE.
25. **Đánh đồng thử nghiệm full oracle trong RAM với runtime production ngoài bộ nhớ**.
26. **Dùng count equality cho phép filter/join mà không có phương trình kế toán riêng**.
27. **Chỉ thử dữ liệu có key phân biệt**, không phát hiện sai stable sort.
28. **Không test giá trị Long.MIN/MAX và tên file thiếu/trùng**, bỏ qua input biên.
29. **Không có generation/jobId/attemptId**, khiến retry ghi đè lên kết quả đang dùng.
30. **Không giới hạn độ dài manifest và số artifact**, có thể vượt RAM khi metadata quá lớn.
31. **Tin file vẫn bất biến sau hash nhưng người khác còn quyền ghi**, có nguy cơ TOCTOU.
32. **Không ghi rõ loại lỗi cần retry hay dừng vĩnh viễn**, khiến dữ liệu sai được chạy lại nhiều lần.
33. **Không tính disk space tạm và peak usage**, hết đĩa giữa một pass.
34. **Lấy số dòng từ input đang bị chỉnh đồng thời mà không snapshot**, khiến một lần đọc không nhất quán.
35. **Không kiểm tra output sau rename và DONE**, bỏ mất bước readback cuối cùng.

## 33. Bài tập tự luyện

**Bài 1 — Run:** với đầu vào 9,1,5,5,-3,12,1 và buffer 3, tự tính ba run chứa các cặp `(key,position)`, rồi k-way merge.

**Bài 2 — Count:** với N=1000, các run có count 250,250,240,260. Kiểm tra stage count; chỉ ra vì sao kết luận đầy đủ vẫn cần giả thiết khác.

**Bài 3 — Counterexample:** dựng hai multiset có count bằng nhau và thứ tự sorted hợp lệ nhưng nội dung khác nhau.

**Bài 4 — Manifest:** viết một định dạng header/RUN/END chứa version, source digest và số dòng; đề xuất cách phát hiện run bị bỏ khỏi manifest.

**Bài 5 — Crash:** mô phỏng crash sau khi ghi một `.partial` nhưng trước rename; khi resume được phép đọc artifact nào?

**Bài 6 — Commit:** vẽ state machine `NEW -> RUNS_READY -> RUNS_VERIFIED -> OUTPUT_READY -> DONE`, quy định file/manifest cần tồn tại ở mỗi trạng thái.

**Bài 7 — Durable:** tìm hiểu khác biệt giữa flush của BufferedWriter, rename nguyên tử và FileChannel.force(true) trên filesystem thực.

**Bài 8 — Fan-in:** với N=100 triệu, buffer chứa 1 triệu bản ghi và F=10, tính số run đầu tiên và số pass merge tối thiểu nếu mỗi pass giảm run theo nhóm 10.

**Bài 9 — Stable sort:** chứng minh comparator `(key,originalPosition)` giữ thứ tự các key bằng nhau sau mọi pass merge.

**Bài 10 — Independent oracle:** với N≤100, sort toàn bộ Row trong RAM và so mọi row với output đã merge.

**Bài 11 — Fault injection:** sửa một byte trong run nhưng giữ số dòng; bước kiểm tra nào phát hiện? Sửa manifest cùng lúc có thể vượt qua điều kiện nào?

**Bài 12 — Audit:** thêm sourceVersion và jobAttempt vào manifest, viết quy tắc không trộn hai phiên bản khác nhau.

**Bài 13 — Delete:** xác định các file được phép xóa sau khi DONE đã được verify mà vẫn giữ khả năng resume/replay như yêu cầu vận hành.

**Bài 14 — ETL filter:** nếu 10.000 input có 100 rejected và 900 filtered, output phải có bao nhiêu? Viết đẳng thức kế toán.

**Bài 15 — Multi-pass:** hiện thực merge từng nhóm tối đa F run thành một run mới và commit manifest cho **mỗi pass**, không xóa run cũ trước khi pass kế đã verify.

**Bài 16 — Zero input:** giải thích vì sao manifest không có RUN, sorted.dat rỗng và DONE count0 vẫn là output hợp lệ.

**Bài 17 — I/O cost:** với block B và memory M, phân biệt thời gian CPU với số lần truyền block trong external sort.

**Bài 18 — Readback:** khi DONE ghi count và SHA-256, liệt kê thêm những kiểm tra phải thực hiện để biết output có sortedness đúng.

## 34. Checklist cuối bài và kết luận

Trước khi công bố một giai đoạn xử lý ngoài bộ nhớ hoàn thành, cần trả lời:

- **Nguồn nào?** Có source version/snapshot và provenance rõ không?
- **Stage tạo bao nhiêu artifact?** Manifest có đủ danh sách và tên duy nhất không?
- **Artifact đã commit chưa?** Có tách file `.partial` khỏi bản sẵn sàng không?
- **Có kiểm tra bytes và nội dung?** SHA-256, count, schema, sortedness hoặc bất biến chuyên biệt có đúng không?
- **Các bản ghi đi đâu?** Có phương trình bảo toàn và chứng cứ không mất/nhân đôi record không?
- **Fan-in và bộ nhớ có đủ?** Nếu không đủ thì fail fast hoặc lên kế hoạch multi-pass.
- **Kết quả cuối đã verify chưa?** Có DONE marker, readback count/hash và kiểm tra tính hợp lệ của output không?
- **Nếu crash thì sao?** File nào có thể dùng lại, file nào là orphan, checkpoint nào còn hiệu lực?
- **Nếu có đối thủ hoặc writer cạnh tranh?** Manifest/hash có nguồn tin cậy và cơ chế bất biến dữ liệu không?
- **Đã test được tình huống lỗi chưa?** Có oracle độc lập và fault injection cho file hỏng, thiếu DONE, nguồn đổi và dữ liệu biên không?

**Kết luận:** Trong các thuật toán ngoài bộ nhớ, quản lý kết quả trung gian là một phần của **tính đúng**, không phải chuyện dọn file tạm sau khi thuật toán đã xong. Manifest giúp biết artifact nào thuộc một stage; count và SHA-256 phát hiện nhiều lỗi, nhưng phải kết hợp với **bất biến thuật toán và provenance** để chứng minh completeness. Chỉ sau khi các artifact đã được ghi, verify, commit, và output cuối được readback đúng thì pipeline mới có thể báo hoàn thành. Đó là nền tảng để xây external sort, ETL, MapReduce và các hệ thống xử lý dữ liệu lớn có khả năng phục hồi.
