# Chạy ứng dụng với `-XX:CRaCCheckpointTo`

Trong chu kỳ checkpoint–restore của CRaC (Coordinated Restore at Checkpoint), JVM cần biết nơi lưu ảnh checkpoint của tiến trình. Tùy chọn `-XX:CRaCCheckpointTo` dùng để chỉ định thư mục đích đó khi khởi chạy ứng dụng. Sau khi ứng dụng đã sẵn sàng cho checkpoint, ta gửi lệnh `JDK.checkpoint` qua `jcmd` để yêu cầu JVM tạo ảnh trạng thái. Khi cần chạy lại ứng dụng từ ảnh đã lưu, ta khởi chạy JVM bằng tùy chọn `-XX:CRaCRestoreFrom` trỏ đến cùng checkpoint.

Hai tùy chọn này phục vụ hai giai đoạn khác nhau:

| Tùy chọn | Giai đoạn | Công dụng |
| --- | --- | --- |
| `-XX:CRaCCheckpointTo=<path>` | Khởi chạy để chuẩn bị tạo checkpoint | Khai báo vị trí lưu checkpoint. Bản thân tùy chọn này không tự tạo checkpoint. |
| `-XX:CRaCRestoreFrom=<path>` | Khởi chạy để restore | Yêu cầu JVM khôi phục tiến trình từ checkpoint đã có tại vị trí được chỉ định. |

Ví dụ trong bài dùng lệnh Linux và một ứng dụng đóng gói thành JAR. CRaC phụ thuộc vào bản JDK có hỗ trợ CRaC và khả năng checkpoint của hệ điều hành; hãy thực hiện trên môi trường Linux được bản JDK/CRaC của bạn hỗ trợ.

## 1. Cú pháp và vị trí của tùy chọn

Cú pháp cơ bản:

```bash
java -XX:CRaCCheckpointTo=/path/to/checkpoint -jar application.jar
```

`/path/to/checkpoint` là đường dẫn mà JVM sử dụng làm đích lưu ảnh checkpoint. Hãy dùng một đường dẫn rõ ràng, có thể truy cập được bởi user chạy JVM và nằm trên filesystem phù hợp với cơ chế checkpoint của runtime. Thư mục cha phải tồn tại; tiến trình cần đủ quyền để tạo và ghi dữ liệu checkpoint tại vị trí đích.

Tùy chọn `-XX:CRaCCheckpointTo` là JVM option nên phải đặt trước `-jar`:

```bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoints/release-1 \
  -Xms512m \
  -Xmx512m \
  -jar application.jar \
  --spring.profiles.active=production
```

Trong ví dụ này:

- `-XX:CRaCCheckpointTo=...`, `-Xms512m` và `-Xmx512m` là các tùy chọn của JVM.
- `-jar application.jar` chỉ định file JAR cần chạy.
- `--spring.profiles.active=production` là tham số của ứng dụng Spring Boot, được đặt sau tên JAR.

Nếu đặt `-XX:CRaCCheckpointTo` sau `-jar`, JVM sẽ không còn đọc nó như một JVM option; tùy theo ứng dụng, chuỗi đó có thể bị truyền vào `main(String[] args)` như một tham số ứng dụng. Vì vậy, cần phân biệt ranh giới giữa JVM options và application arguments.

Đường dẫn có dấu cách cần được quote theo quy tắc của shell:

```bash
java "-XX:CRaCCheckpointTo=/var/lib/my app/checkpoint" -jar application.jar
```

Nên ưu tiên đường dẫn đơn giản, ổn định và không phụ thuộc thư mục làm việc hiện tại để giảm lỗi khi vận hành tự động.

## 2. Chuẩn bị môi trường trước khi chạy

`-XX:CRaCCheckpointTo` chỉ có ý nghĩa khi JVM đang chạy là bản có hỗ trợ CRaC. Một JDK thông thường không nhất thiết nhận biết tùy chọn này. Trước khi triển khai, cần xác nhận các điều kiện sau:

1. **JDK hỗ trợ CRaC:** dùng đúng distribution và phiên bản JDK có tích hợp CRaC. Giữ thông tin phiên bản để dùng lại khi restore.
2. **Hệ điều hành và kernel tương thích:** CRaC dựa trên cơ chế checkpoint tiến trình của nền tảng. Trên Linux, môi trường thường cần CRIU cùng các tính năng kernel phù hợp. Cấu hình cụ thể phụ thuộc distribution, kernel, container runtime và bản JDK.
3. **Quyền truy cập:** user chạy JVM phải có quyền ghi checkpoint và quyền truy cập các file, thư mục, thư viện mà tiến trình cần khi restore.
4. **Dung lượng lưu trữ:** checkpoint có thể chứa lượng lớn trạng thái bộ nhớ của tiến trình. Cần dự trù dung lượng, I/O và thời gian tạo ảnh.
5. **Đường dẫn ổn định:** chọn nơi lưu mà tiến trình restore có thể truy cập lại. Nếu chạy trong container, đường dẫn cần được ánh xạ tới storage còn tồn tại sau khi container cũ dừng hoặc bị thay thế.
6. **Tài nguyên ứng dụng:** xác định cách ứng dụng xử lý socket, kết nối database, thread, file handle và tài nguyên bên ngoài qua lifecycle checkpoint/restore.

Có thể kiểm tra phiên bản Java trước khi chạy:

```bash
java -version
```

Sau khi ứng dụng chạy, dùng `jcmd` từ cùng JDK để xem các lệnh diagnostic mà JVM cung cấp:

```bash
jcmd <pid> help
```

Trên runtime CRaC phù hợp, danh sách lệnh cần có `JDK.checkpoint`. Nếu tùy chọn `-XX:CRaCCheckpointTo` bị báo là unrecognized hoặc lệnh `JDK.checkpoint` không tồn tại, hãy kiểm tra lại distribution JDK, phiên bản và cấu hình CRaC trước khi tiếp tục.

## 3. Khởi chạy ứng dụng với thư mục checkpoint

Giả sử ứng dụng được đóng gói tại `/opt/myapp/application.jar` và checkpoint sẽ được lưu tại `/var/lib/myapp/checkpoints/release-1`.

```bash
APP_JAR=/opt/myapp/application.jar
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1

java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar "$APP_JAR" &
APP_PID=$!
```

Giải thích:

- `APP_JAR` giữ đường dẫn file JAR để lệnh chạy dễ đọc và tránh lặp lại chuỗi đường dẫn.
- `CHECKPOINT_DIR` là vị trí sẽ được sử dụng cho checkpoint.
- Dấu `&` chạy JVM ở background trong shell hiện tại.
- `$!` lấy PID của tiến trình vừa được shell khởi chạy. Cách này phù hợp khi lệnh `java` trực tiếp tạo tiến trình ứng dụng, không đi qua một script wrapper tự fork hoặc daemonize.

Nếu ứng dụng chạy dưới service manager, container hoặc một hệ thống orchestration, hãy lấy PID thực tế của JVM trong đúng process namespace. PID trên host có thể khác PID nhìn thấy bên trong container.

Sau khi khởi chạy, kiểm tra log và chờ ứng dụng hoàn tất các bước khởi tạo. Có thể dùng:

```bash
jcmd -l
```

Lệnh này liệt kê các JVM mà `jcmd` có thể nhận diện. Đối chiếu PID với đúng ứng dụng trước khi gửi lệnh checkpoint. Không chọn nhầm PID của một JVM khác đang chạy trên cùng máy.

## 4. Yêu cầu JVM tạo checkpoint

Khi ứng dụng đã sẵn sàng, yêu cầu checkpoint bằng:

```bash
jcmd "$APP_PID" JDK.checkpoint
```

`jcmd` kết nối tới JVM có PID tương ứng và gửi diagnostic command `JDK.checkpoint`. JVM sẽ phối hợp với CRaC để chạy quy trình checkpoint, bao gồm các callback chuẩn bị tài nguyên đã đăng ký, rồi ghi trạng thái tiến trình vào vị trí được khai báo bởi `-XX:CRaCCheckpointTo`.

Điểm cần nhớ là `-XX:CRaCCheckpointTo` chỉ cấu hình đích lưu. Lệnh `JDK.checkpoint` mới là yêu cầu thực hiện checkpoint. Nếu ứng dụng chỉ được khởi chạy với tùy chọn này nhưng không có yêu cầu checkpoint, ảnh checkpoint sẽ không tự xuất hiện chỉ vì JVM đã chạy một khoảng thời gian.

Khi checkpoint thành công, tiến trình gốc thường kết thúc theo quy trình checkpoint của CRaC để tránh tiếp tục chạy đồng thời với tiến trình sẽ được khôi phục từ cùng ảnh trạng thái. Hãy kiểm tra kết quả lệnh, log của JVM và trạng thái tiến trình thay vì giả định ứng dụng vẫn đang phục vụ request như trước.

Các bước kiểm tra ở mức vận hành:

```bash
# Xem lại các JVM đang chạy
jcmd -l

# Kiểm tra nội dung thư mục checkpoint
find "$CHECKPOINT_DIR" -maxdepth 2 -type f -print
```

Tên và cấu trúc file bên trong checkpoint do runtime/CRIU quản lý; ứng dụng không nên tự chỉnh sửa hoặc xóa từng file bên trong ảnh checkpoint. Cũng không nên coi sự tồn tại của thư mục là bằng chứng duy nhất rằng checkpoint hợp lệ. Cần kiểm tra lệnh checkpoint đã hoàn tất và thử restore trong môi trường phù hợp.

## 5. Khôi phục ứng dụng từ checkpoint

Sau khi có checkpoint, khởi chạy JVM bằng tùy chọn restore:

```bash
java -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

`-XX:CRaCRestoreFrom` trỏ tới ảnh checkpoint đã tạo trước đó. JVM khôi phục tiến trình và tiếp tục từ trạng thái được lưu. Đây là một lần khôi phục tiến trình, không phải một lần chạy `application.jar` mới từ đầu; vì vậy, lệnh restore không cần thêm `-jar application.jar` như lệnh khởi chạy ban đầu.

Sau restore, ứng dụng tiếp tục vòng đời runtime theo trạng thái đã lưu và thực hiện các xử lý sau restore mà ứng dụng hoặc thư viện CRaC đã đăng ký. Cần kiểm tra log, readiness và khả năng xử lý request trước khi đưa instance vào nhận traffic.

Ví dụ luồng thao tác đầy đủ:

```bash
# 1. Khởi chạy ứng dụng và cấu hình nơi lưu checkpoint
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1
java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar /opt/myapp/application.jar &
APP_PID=$!

# 2. Chờ ứng dụng sẵn sàng và gửi workload chuẩn bị nếu cần
#    Thay bước này bằng health check/warm-up phù hợp với ứng dụng.

# 3. Yêu cầu tạo checkpoint
jcmd "$APP_PID" JDK.checkpoint

# 4. Khi cần restore, chạy lệnh trong môi trường tương thích
java -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

Đây là ví dụ minh họa chuỗi lệnh; trong thực tế, bước restore thường được thực hiện ở một lần triển khai hoặc một tiến trình khởi động khác sau khi checkpoint đã được lưu trữ an toàn.

## 6. Vai trò của lifecycle hook trong lúc checkpoint và restore

Một ảnh checkpoint lưu trạng thái tiến trình, nhưng không làm cho mọi tài nguyên bên ngoài tự động hợp lệ khi tiến trình tiếp tục chạy. Ứng dụng cần phối hợp với CRaC để chuẩn bị trước checkpoint và phục hồi tài nguyên sau restore.

Về mặt khái niệm, lifecycle gồm hai thời điểm quan trọng:

| Thời điểm | Mục tiêu | Ví dụ xử lý |
| --- | --- | --- |
| Trước checkpoint (`beforeCheckpoint`) | Đưa tài nguyên về trạng thái có thể lưu và khôi phục | Hoàn tất hoặc dừng công việc đang chạy, đóng kết nối không thể tái sử dụng, flush dữ liệu cần thiết và dừng thread/timer phù hợp. |
| Sau restore (`afterRestore`) | Khôi phục hoặc kiểm tra tài nguyên cần cho hoạt động tiếp theo | Tạo lại connection pool, mở lại kết nối database/socket, làm mới thông tin phụ thuộc môi trường và khởi động lại tác vụ phù hợp. |

Framework hoặc thư viện có tích hợp CRaC có thể tự quản lý một số tài nguyên. Với tài nguyên do ứng dụng tự tạo, cần kiểm tra xem chúng đã được đăng ký và xử lý đúng lifecycle hay chưa. Không nên giả định rằng một JDBC connection, socket hoặc file descriptor sẽ luôn dùng được sau restore chỉ vì object Java tương ứng vẫn còn trong heap.

Khi gọi `jcmd <pid> JDK.checkpoint`, callback chuẩn bị có thể phát hiện ứng dụng chưa sẵn sàng và làm checkpoint thất bại. Đây là cơ chế bảo vệ có chủ đích: tốt hơn hết là sửa cách quản lý tài nguyên hoặc thời điểm checkpoint thay vì bỏ qua lỗi rồi tạo một ảnh trạng thái không an toàn.

## 7. Chọn thời điểm checkpoint

Đặt `-XX:CRaCCheckpointTo` khi khởi chạy mới chỉ giải quyết vị trí lưu. Chất lượng checkpoint còn phụ thuộc vào thời điểm gửi `JDK.checkpoint`.

Nếu checkpoint ngay sau khi JVM bắt đầu chạy, ảnh trạng thái có thể chưa chứa đầy đủ cache ứng dụng, class đã nạp hoặc trạng thái JIT hữu ích. Nếu checkpoint sau khi ứng dụng xử lý workload đại diện, trạng thái runtime có thể phù hợp hơn với giai đoạn nhận traffic đầu tiên sau restore.

Một quy trình chuẩn bị thường gồm:

1. Khởi chạy ứng dụng với `-XX:CRaCCheckpointTo` trỏ đến thư mục checkpoint dành riêng cho phiên bản triển khai.
2. Chờ ứng dụng hoàn tất startup và các health check cần thiết.
3. Thực hiện warm-up đại diện nếu mục tiêu là giữ lại trạng thái cache/JIT có ích cho traffic sau restore.
4. Xác nhận không còn giao dịch hoặc tác vụ cần hoàn tất theo cách không tương thích với checkpoint.
5. Gửi `jcmd <pid> JDK.checkpoint`.
6. Xác nhận checkpoint thành công và thử restore bằng đúng runtime tương thích.

Warm-up cần tránh side effect ngoài ý muốn. Nếu endpoint làm thay đổi dữ liệu, gửi thông báo hoặc tạo giao dịch, hãy dùng dữ liệu kiểm thử và cơ chế cô lập phù hợp. Không nên tạo checkpoint khi ứng dụng đang ở giữa một thao tác nghiệp vụ mà việc tiếp tục sau restore có thể gây lặp hoặc mất dữ liệu.

## 8. Vận hành trong container và môi trường triển khai

Trong container, đường dẫn checkpoint thường nên đặt trên volume được mount từ bên ngoài container hoặc một vùng lưu trữ có vòng đời đủ dài. Nếu checkpoint chỉ nằm trong writable layer của container cũ, việc xóa hoặc thay thế container có thể làm mất ảnh checkpoint.

Ví dụ cấu hình đường dẫn ở cấp ứng dụng:

```bash
java -XX:CRaCCheckpointTo=/checkpoint/release-1 -jar application.jar
```

Ở đây `/checkpoint` cần được mount vào container và có quyền truy cập phù hợp. Ngoài việc mount thư mục, môi trường container còn phải đáp ứng yêu cầu CRaC/CRIU và quyền kernel cần thiết. Chỉ mount volume không tự động làm cho checkpoint tiến trình được hỗ trợ trong mọi container runtime.

Khi gọi `jcmd`, hãy thực hiện trong đúng môi trường process namespace và dùng quyền phù hợp với user sở hữu JVM. Nếu PID của JVM trong container là `1`, lệnh trong container có thể dùng PID `1`; không được mặc định PID trên host cũng là `1`.

Checkpoint phụ thuộc vào môi trường runtime. Khi chuyển ảnh sang host khác, cần bảo đảm mức tương thích của JDK, kiến trúc CPU, kernel, thư viện native, đường dẫn mount và các tài nguyên mà ứng dụng cần. Không nên xem checkpoint như một file JAR portable có thể restore tùy ý trên bất kỳ máy nào.

Vì checkpoint có thể chứa heap và trạng thái bộ nhớ của ứng dụng, nó có thể bao gồm token, mật khẩu, dữ liệu người dùng hoặc thông tin nhạy cảm khác đang nằm trong bộ nhớ. Hãy kiểm soát quyền đọc/ghi, bảo vệ storage, chính sách lưu giữ và quy trình xóa checkpoint cũ như đối với dữ liệu nhạy cảm.

## 9. Lỗi thường gặp và hướng kiểm tra

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `Unrecognized VM option 'CRaCCheckpointTo'` | JDK đang dùng không hỗ trợ tùy chọn CRaC hoặc sai tên/cú pháp tùy chọn | Xác nhận distribution và phiên bản JDK CRaC; kiểm tra chính tả `-XX:CRaCCheckpointTo=<path>`. |
| `jcmd` không tìm thấy PID | Dùng sai PID, JVM đã dừng hoặc đang ở process namespace khác | Chạy `jcmd -l` trong đúng môi trường; kiểm tra process manager/container và lấy PID của JVM thực tế. |
| `JDK.checkpoint` không có trong danh sách lệnh | Runtime không tích hợp CRaC hoặc lệnh không được cung cấp trong bản đang chạy | Kiểm tra `jcmd <pid> help`, phiên bản JDK và tài liệu của distribution. |
| Không ghi được checkpoint | Đường dẫn không hợp lệ, thiếu quyền, filesystem hoặc môi trường không đáp ứng yêu cầu | Kiểm tra quyền user, dung lượng, mount, filesystem, kernel và cấu hình CRIU. |
| Checkpoint bị từ chối bởi resource | Một tài nguyên chưa được chuẩn bị hoặc callback `beforeCheckpoint` thất bại | Đọc log và sửa lifecycle của tài nguyên; thử checkpoint lại khi ứng dụng ở trạng thái an toàn. |
| Restore thất bại trên host khác | Khác biệt JDK, kiến trúc, kernel, thư viện native, mount hoặc tài nguyên môi trường | Khôi phục trên môi trường tương thích và kiểm tra đầy đủ dependency của tiến trình. |
| Ứng dụng lỗi sau khi restore | Resource chưa được tạo lại hoặc callback `afterRestore` xử lý chưa đúng | Kiểm tra log restore, connection pool, socket, file handle và các tác vụ nền. |

Khi điều tra, nên lưu lại phiên bản JDK, lệnh khởi chạy, đường dẫn checkpoint, log từ trước checkpoint đến sau restore và thông tin môi trường host/container. Những dữ liệu này giúp phân biệt lỗi do cú pháp tùy chọn, quyền truy cập, CRIU hay lifecycle của ứng dụng.

## 10. Checklist vận hành

Trước khi tạo checkpoint, xác nhận:

- [ ] Đang dùng JDK có hỗ trợ CRaC và đúng phiên bản dự kiến cho restore.
- [ ] `-XX:CRaCCheckpointTo` được đặt trước `-jar` và trỏ đến đường dẫn hợp lệ.
- [ ] User chạy JVM có quyền ghi checkpoint và storage còn đủ dung lượng.
- [ ] Kernel, CRIU, container runtime và filesystem đáp ứng yêu cầu của môi trường.
- [ ] Ứng dụng đã hoàn tất startup và workload warm-up cần thiết.
- [ ] Các tài nguyên đã đăng ký lifecycle hook và có thể xử lý checkpoint/restore.
- [ ] Không có side effect hoặc giao dịch đang dở có thể gây sai lệch khi restore.
- [ ] Đã xác định cách bảo vệ, lưu giữ và truy cập ảnh checkpoint.

Sau khi checkpoint, xác nhận:

- [ ] `jcmd <pid> JDK.checkpoint` hoàn tất mà không có lỗi.
- [ ] Log thể hiện quá trình checkpoint đã thành công.
- [ ] Ảnh checkpoint nằm tại đúng đường dẫn đã cấu hình.
- [ ] Restore được thử bằng `-XX:CRaCRestoreFrom=<path>` trên môi trường tương thích.
- [ ] Ứng dụng hoàn tất xử lý sau restore và vượt qua readiness check.
- [ ] Các endpoint quan trọng, kết nối và tác vụ nền hoạt động bình thường.

## 11. Kết luận

`-XX:CRaCCheckpointTo` là JVM option dùng để khai báo nơi lưu checkpoint khi khởi chạy ứng dụng. Nó không tự tạo ảnh checkpoint. Sau khi ứng dụng đã sẵn sàng và tài nguyên đã được chuẩn bị, dùng `jcmd <pid> JDK.checkpoint` để yêu cầu JVM thực hiện checkpoint. Khi cần khôi phục, khởi chạy bằng `-XX:CRaCRestoreFrom=<path>` để tiếp tục tiến trình từ ảnh đã lưu.

Để chu kỳ này hoạt động ổn định, cần phối hợp đúng JDK CRaC, kernel/CRIU, filesystem, quyền truy cập và lifecycle tài nguyên của ứng dụng. Hãy xác nhận checkpoint bằng một lần restore thực tế trên môi trường tương thích; việc chỉ nhìn thấy thư mục checkpoint hoặc thấy lệnh khởi chạy không báo lỗi chưa đủ chứng minh ứng dụng có thể khôi phục thành công.
