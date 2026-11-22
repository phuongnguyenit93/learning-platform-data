# Chọn phiên bản MySQL và tài nguyên cho môi trường học

Bài học thuộc chương **Môi trường thực hành** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Vì vậy, môi trường học cần đủ ổn định để các ví dụ SQL cho kết quả nhất quán, đồng thời đủ linh hoạt để tạo dữ liệu, thử cấu hình và khôi phục sau mỗi bài thực hành.

Sau bài này, bạn có thể chọn một nhánh phát hành MySQL phù hợp, quyết định cài trực tiếp hay chạy bằng container, ước lượng tài nguyên máy, khởi động một môi trường mẫu và xác nhận máy chủ đang chạy đúng phiên bản.

## 1. Vì sao phải chọn phiên bản trước khi thực hành?

MySQL Server là chương trình lưu trữ và xử lý dữ liệu. MySQL client, MySQL Workbench và connector là các công cụ kết nối tới Server. Phiên bản của chúng không nhất thiết giống nhau, nhưng cần tương thích với nhau.

Khác biệt giữa các phiên bản Server có thể ảnh hưởng đến cú pháp SQL, từ khóa được dành riêng, kiểu dữ liệu, giá trị mặc định, cơ chế xác thực, collation, optimizer và kế hoạch thực thi. Một câu lệnh chạy được trên máy này có thể cảnh báo hoặc cho kết quả hiệu năng khác trên máy khác nếu hai máy dùng cấu hình hay phiên bản khác nhau.

Trong quá trình học, hãy ghi nhận tối thiểu:

- Phiên bản MySQL Server mà bài tập đang sử dụng.
- Cách cài đặt: cài trực tiếp, container hay dịch vụ quản lý trên cloud.
- Cổng kết nối, tên database và tài khoản thực hành.
- Charset, collation và các cấu hình quan trọng nếu bài học phụ thuộc vào chúng.

Không dùng phiên bản của chương trình client để kết luận phiên bản Server. Lệnh `mysql --version` cho biết phiên bản client đang chạy; truy vấn `SELECT VERSION();` mới cho biết phiên bản Server của kết nối hiện tại.

## 2. Chọn nhánh phát hành MySQL

MySQL hiện có hai nhánh phát hành chính: **LTS (Long-Term Support)** và **Innovation**. Cả hai đều có bản sửa lỗi và bảo mật. Khác biệt chính nằm ở mức độ ổn định của tập tính năng và nhịp nâng cấp.

| Tiêu chí | LTS | Innovation |
|---|---|---|
| Mục tiêu | Môi trường cần tập tính năng ổn định trong thời gian dài | Thử nghiệm tính năng và thay đổi mới |
| Thay đổi hành vi | Hạn chế thay đổi trong cùng một dòng LTS | Có thể thay đổi hành vi, cú pháp hoặc cách tối ưu giữa các bản phát hành |
| Nhịp nâng cấp | Nâng cấp bảo trì trong cùng dòng; lên dòng LTS kế tiếp theo lộ trình | Hỗ trợ đến khi có bản Innovation kế tiếp |
| Phù hợp với | Học tập có lộ trình, ứng dụng cần tương thích ổn định, môi trường dài hạn | Nghiên cứu tính năng mới, thử nghiệm có kiểm thử tự động và kế hoạch nâng cấp thường xuyên |

### Lựa chọn đề xuất tại thời điểm 19-11-2026

Với môi trường mới dành cho người học, chọn **MySQL 9.7 LTS** làm phiên bản mặc định. Docker Official Image hiện liệt kê tag `9.7.4` cho nhánh này. Nếu một dự án hoặc tài liệu cụ thể yêu cầu MySQL 8.4, hãy dùng một bản vá 8.4.x tương ứng thay vì tự ý đổi sang 9.7.

Nhánh Innovation hiện được Docker Official Image liệt kê là `26.10.0`. Chỉ chọn nhánh này khi mục tiêu của bài tập là thử nghiệm tính năng mới hoặc kiểm tra khả năng tương thích với bản phát hành Innovation. Không dùng nó làm mặc định cho toàn bộ lộ trình nhập môn nếu không có yêu cầu cụ thể.

MySQL 9.7 là dòng cuối cùng dùng cách đánh số tuần tự cũ. Các dòng Innovation và LTS tiếp theo sử dụng cách đánh số theo năm và tháng, dạng YY.M.P (năm, tháng phát hành và số bản vá). Vì vậy, khi đọc phiên bản, cần kiểm tra rõ nhánh phát hành thay vì suy luận chỉ từ số lớn hay nhỏ.

### Cố định phiên bản để tái lập kết quả

Nếu dùng Docker, chọn tag cụ thể, ví dụ `mysql:9.7.4`, để mọi lần tạo môi trường đều bắt đầu từ cùng một bản vá. Tag `9.7` có thể được cập nhật lên bản vá mới trong dòng 9.7; tag `latest` có thể chuyển sang nhánh khác. Tại thời điểm viết bài, Docker Official Image gắn `latest` với dòng Innovation 26.10.0, không phải LTS.

Khi cần cập nhật bản vá bảo mật, hãy chủ động kiểm tra release notes, đổi tag, sao lưu dữ liệu và chạy lại các bài kiểm tra. Không nâng cấp Server giữa chừng một bài thực hành rồi so sánh kết quả như thể môi trường không thay đổi.

Quy tắc chọn nhanh:

1. Bài học mới, không có ràng buộc tương thích: chọn MySQL 9.7 LTS.
2. Dự án hoặc bài tập yêu cầu MySQL 8.4: chọn đúng dòng 8.4 LTS.
3. Bài học thử nghiệm tính năng mới: chọn nhánh Innovation và ghi rõ phiên bản trong báo cáo.
4. Dự án đã có dữ liệu hoặc hệ thống đang chạy: kiểm tra đường nâng cấp và sao lưu trước khi thay đổi phiên bản.

## 3. Chọn cách chạy MySQL

Có ba cách phổ biến để tạo môi trường thực hành. Không có một lựa chọn phù hợp cho mọi tình huống; hãy chọn theo mục tiêu của bài học và công cụ sẵn có trên máy.

| Cách chạy | Khi nào nên chọn | Ưu điểm | Điểm cần lưu ý |
|---|---|---|---|
| Cài trực tiếp trên Windows, Linux hoặc macOS | Muốn học cách cài đặt, cấu hình service, xem log và quản lý tiến trình của hệ điều hành | Truy cập trực tiếp, ít lớp trung gian, dễ tích hợp công cụ trên máy | Có thể xung đột với MySQL đã cài, cổng 3306 hoặc thư mục dữ liệu; đổi phiên bản và dọn môi trường mất công hơn |
| Docker / Docker Compose | Muốn tạo môi trường giống nhau trên nhiều máy hoặc chạy nhiều phiên bản độc lập | Cố định image, cô lập dịch vụ, tạo và dừng môi trường nhanh, dữ liệu có thể lưu trong volume | Cần Docker Engine hoặc Docker Desktop; phải hiểu port mapping và volume |
| MySQL trên dịch vụ cloud | Muốn luyện kết nối từ xa, mạng, quyền truy cập, backup hoặc vận hành dịch vụ được quản lý | Không phải tự quản lý máy chủ vật lý; có thể mô phỏng cách ứng dụng kết nối database từ xa | Có thể phát sinh chi phí, yêu cầu tài khoản và cấu hình mạng; phải bảo vệ thông tin xác thực và dữ liệu |

**Khuyến nghị cho phần lớn bài thực hành:** dùng Docker Compose nếu máy đã có Docker. Mỗi bài có thể khởi động một môi trường độc lập, dùng tag phiên bản rõ ràng và giữ dữ liệu trong volume. Nếu chưa quen Docker hoặc bài học tập trung vào quản lý service của hệ điều hành, cài MySQL trực tiếp cũng là lựa chọn hợp lý.

Không cần dùng cloud chỉ để chạy các câu lệnh SQL cơ bản. Hãy chuyển sang cloud khi bài học thực sự cần kết nối qua mạng hoặc thao tác với dịch vụ database được quản lý.

## 4. Chuẩn bị công cụ kết nối

Một môi trường học tối thiểu gồm:

- **MySQL Server:** tiến trình database mà các bài tập sẽ thao tác.
- **MySQL command-line client:** chạy SQL trực tiếp, phù hợp để làm quen câu lệnh, ghi lại kết quả và tự động hóa.
- **MySQL Workbench:** giao diện đồ họa để quản lý kết nối, viết SQL, thiết kế mô hình dữ liệu và thực hiện một số thao tác quản trị.
- **Terminal:** chạy Docker Compose hoặc các lệnh quản lý dịch vụ.

Nên cài phiên bản MySQL Workbench mới nhất được cung cấp trên trang tải chính thức và kiểm tra khả năng tương thích với Server đang dùng. Tại thời điểm viết bài, trang tải chính thức liệt kê Workbench 26.10.0 và ghi nhận phiên bản mới nhất tương thích ngược với các phiên bản MySQL Server còn được hỗ trợ.

Khi tạo kết nối Workbench tới MySQL chạy trên máy cá nhân, thông tin thường dùng là:

| Trường | Giá trị trong môi trường mẫu |
|---|---|
| Connection Method | Standard TCP/IP |
| Hostname | `127.0.0.1` |
| Port | `3306` |
| Username | `learner` |
| Password | Nhập mật khẩu của tài khoản learner |
| Default Schema | `mysql_lab` |

Dùng tài khoản riêng cho bài tập. Chỉ dùng `root` khi cần thao tác quản trị hoặc tạo tài khoản; không dùng tài khoản quản trị cho các truy vấn thông thường.

## 5. Ước lượng tài nguyên máy

Tài nguyên cần thiết phụ thuộc vào kích thước dữ liệu, số kết nối đồng thời, số dịch vụ chạy cùng lúc và loại bài tập. Các mức dưới đây là **mốc đề xuất để học trên máy cá nhân**, không phải cấu hình tối thiểu chính thức do Oracle công bố.

| Quy mô thực hành | Máy chủ (host) nên có | Phân bổ tham khảo cho MySQL |
|---|---|---|
| Bài SQL cơ bản, một người học, dữ liệu nhỏ | 2 lõi CPU, RAM 8 GB, còn ít nhất 10 GB dung lượng SSD | 1–2 lõi CPU, RAM khoảng 1–2 GB, volume dữ liệu riêng |
| Bài có nhiều bảng, index, transaction, EXPLAIN và dữ liệu lớn hơn | 4 lõi CPU, RAM 16 GB, còn 20–30 GB SSD | 2–4 lõi CPU, RAM khoảng 2–4 GB, tăng dung lượng volume theo dữ liệu |
| Chạy thêm ứng dụng, cache, message broker hoặc nhiều database | 4 lõi CPU trở lên, RAM 16 GB trở lên | Phân bổ riêng cho từng dịch vụ; theo dõi CPU, RAM, I/O và dung lượng đĩa |

Một vài nguyên tắc phân bổ:

- **RAM:** MySQL dùng bộ nhớ cho buffer pool, kết nối, bộ nhớ tạm và các hoạt động nội bộ. Nếu máy chỉ có 8 GB RAM, hãy bắt đầu với cấu hình nhỏ và đóng các dịch vụ không cần thiết. Khi học tối ưu truy vấn với dữ liệu lớn, tăng RAM có thể giúp giảm đọc đĩa nhưng không thay thế việc thiết kế index hợp lý.
- **CPU:** 2 lõi đủ để bắt đầu với một người học và dữ liệu nhỏ. Nhiều lõi hơn hữu ích khi chạy nhiều truy vấn đồng thời hoặc nhiều dịch vụ; tăng CPU không tự động làm một truy vấn đơn lẻ nhanh hơn.
- **SSD và dung lượng:** đặt dữ liệu trên SSD nếu có thể. Dành chỗ cho database, binary log nếu bật, file dump và dữ liệu mẫu. Không để volume đầy vì MySQL có thể ngừng ghi dữ liệu.
- **Tài nguyên cho Docker:** phần RAM và CPU cấp cho Docker phải đủ cho MySQL nhưng vẫn chừa tài nguyên cho hệ điều hành, IDE, trình duyệt và các công cụ học tập.
- **Dữ liệu:** bắt đầu bằng bộ dữ liệu nhỏ để kiểm tra câu lệnh. Chỉ tăng lên hàng triệu bản ghi khi bài tập cần đo tác động của index, join hoặc kế hoạch thực thi.

Không nên áp một cấu hình máy chủ sản xuất lớn vào laptop học tập. Hãy đo mức sử dụng thực tế, tăng từng tài nguyên và ghi lại cấu hình khi so sánh hiệu năng.

## 6. Tạo môi trường MySQL 9.7 LTS bằng Docker Compose

Ví dụ sau tạo một database `mysql_lab`, một tài khoản thực hành `learner`, mở cổng chỉ trên loopback của máy và lưu dữ liệu bằng named volume. Cấu hình này dành cho học tập trên máy cá nhân.

Tạo thư mục riêng cho môi trường, sau đó lưu nội dung sau thành `compose.yaml`:

~~~yaml
services:
  db:
    image: mysql:9.7.4
    container_name: mysql-lab
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: mysql_lab
      MYSQL_USER: learner
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "127.0.0.1:3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_0900_ai_ci

volumes:
  mysql_data:
~~~

Tạo file `.env` cùng thư mục:

~~~dotenv
MYSQL_ROOT_PASSWORD=replace_with_a_local_root_password
MYSQL_PASSWORD=replace_with_a_local_learner_password
~~~

Thay hai giá trị mẫu bằng mật khẩu riêng cho máy thực hành. Không commit file `.env` lên Git và không dùng lại mật khẩu của tài khoản thật. Với dự án dùng chung hoặc môi trường có dữ liệu quan trọng, hãy dùng cơ chế quản lý secret phù hợp thay vì lưu mật khẩu dạng văn bản trong repository.

Chạy các lệnh sau từ thư mục chứa `compose.yaml`:

~~~bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f db
~~~

Lần khởi động đầu tiên, image cần khởi tạo thư mục dữ liệu và database. Hãy chờ log cho biết MySQL đã sẵn sàng nhận kết nối rồi mới mở Workbench hoặc chạy client. Trạng thái container đang chạy chưa chắc đồng nghĩa quá trình khởi tạo database đã hoàn tất.

Kết nối bằng client trong container:

~~~bash
docker compose exec db mysql -u learner -p mysql_lab
~~~

Nhập mật khẩu learner khi được hỏi. Sau đó chạy truy vấn xác nhận:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@port AS server_port,
    @@character_set_server AS character_set_server,
    @@collation_server AS collation_server;
~~~

Kết quả cần cho biết Server đang chạy phiên bản 9.7.x, cổng nội bộ 3306 và bộ ký tự/collation đã cấu hình. Nếu kết nối từ Workbench trên máy host, dùng host `127.0.0.1`, port `3306` và user `learner`.

### Hiểu port mapping và volume

Trong cấu hình:

- `127.0.0.1:3306:3306` ánh xạ cổng 3306 của máy host tới cổng 3306 trong container. Việc bind vào `127.0.0.1` giới hạn kết nối ở máy hiện tại, phù hợp với lab cá nhân.
- `mysql_data:/var/lib/mysql` lưu file database trong named volume. Khi container bị xóa và tạo lại, dữ liệu vẫn còn trong volume.
- `MYSQL_DATABASE`, `MYSQL_USER` và `MYSQL_PASSWORD` được image dùng khi khởi tạo một thư mục dữ liệu mới. Nếu volume đã chứa database, đổi các biến trong `.env` không tự đổi mật khẩu hoặc tạo lại user.

Nếu cổng 3306 đã được một MySQL khác sử dụng, đổi phần bên trái thành cổng 3307:

~~~yaml
ports:
  - "127.0.0.1:3307:3306"
~~~

Khi đó, client trên host phải kết nối tới `127.0.0.1:3307`; cổng trong container vẫn là 3306.

### Dừng và tạo lại môi trường

Dừng container nhưng giữ lại dữ liệu:

~~~bash
docker compose down
~~~

Khởi động lại với dữ liệu cũ:

~~~bash
docker compose up -d
~~~

Chỉ khi chủ động muốn xóa toàn bộ dữ liệu thực hành và tạo database mới từ đầu mới chạy:

~~~bash
docker compose down -v
~~~

Tùy chọn `-v` xóa named volume do Compose quản lý. Mọi database trong volume đó sẽ mất. Trước khi dùng lệnh này, hãy export dữ liệu cần giữ bằng `mysqldump` hoặc một công cụ backup phù hợp.

## 7. Nếu cài MySQL trực tiếp trên máy

Cài trực tiếp phù hợp khi bạn muốn hiểu cách MySQL chạy như một service của hệ điều hành hoặc không muốn cài Docker.

- **Windows:** tải gói MSI 64-bit từ trang MySQL Community Server và làm theo hướng dẫn MySQL Configurator. Kiểm tra service đã chạy và ghi nhớ mật khẩu quản trị đã thiết lập.
- **Linux:** dùng repository chính thức hoặc gói phù hợp với bản phân phối. Chọn đúng nhánh LTS trong cấu hình repository nếu cần nhận các bản cập nhật cùng nhánh.
- **macOS:** dùng gói cài đặt native phù hợp với kiến trúc máy. Kiểm tra hướng dẫn khởi động và dừng MySQL sau khi cài.

Với đa số người học, binary distribution là lựa chọn phù hợp; không cần biên dịch từ source. Trước khi cài, kiểm tra hệ điều hành và kiến trúc CPU có nằm trong danh sách nền tảng được hỗ trợ hay không.

Nếu đã có MySQL trên máy, kiểm tra service và cổng 3306 trước khi cài thêm. Hai Server cùng dùng một cổng TCP trên cùng địa chỉ sẽ gây xung đột. Nếu phải duy trì nhiều phiên bản, Docker thường dễ cô lập hơn.

Sau khi cài, mở terminal và chạy:

~~~bash
mysql --version
~~~

Lệnh này kiểm tra client. Đăng nhập vào Server rồi chạy:

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Ghi lại kết quả để biết Server thực tế đang chạy phiên bản nào và đang lắng nghe trên cổng nào.

## 8. Các lỗi thường gặp khi dựng môi trường

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Không thể kết nối tới `127.0.0.1:3306` | Container chưa sẵn sàng, Server chưa chạy hoặc ánh xạ cổng sai | Xem `docker compose ps`, đọc `docker compose logs db`, kiểm tra host và port |
| Cổng 3306 đã được sử dụng | Một MySQL khác hoặc ứng dụng khác đang chiếm cổng | Dùng cổng host 3307 hoặc dừng service không cần thiết |
| Báo `Access denied` sau khi đổi mật khẩu trong `.env` | Volume cũ giữ tài khoản và mật khẩu đã được tạo từ lần khởi tạo trước | Đăng nhập bằng mật khẩu hiện tại rồi đổi mật khẩu bằng SQL; chỉ xóa volume nếu chấp nhận mất dữ liệu |
| Container chạy nhưng client chưa kết nối được ngay | MySQL đang khởi tạo data directory hoặc nạp dữ liệu mẫu | Chờ log báo sẵn sàng; không gửi truy vấn liên tục trong thời gian khởi tạo |
| Dữ liệu vẫn còn sau khi tạo lại container | Named volume được giữ lại | Đây là hành vi mong muốn; dùng `docker compose down -v` chỉ khi muốn xóa dữ liệu |
| Mất dữ liệu sau khi xóa volume hoặc dùng thư mục tạm | Database không được lưu ở nơi bền vững hoặc volume đã bị xóa | Gắn named volume vào `/var/lib/mysql`, tạo backup định kỳ cho dữ liệu cần giữ |
| Workbench kết nối được nhưng một số thao tác quản trị không hoạt động | Phiên bản hoặc tính năng Workbench không phù hợp với Server | Cập nhật Workbench và kiểm tra tài liệu tương thích; dùng mysql client để xác minh trực tiếp |

## 9. Kiểm tra môi trường trước khi bắt đầu bài SQL

Trước khi thực hiện các bài về thiết kế bảng, khóa, index, transaction hoặc tối ưu truy vấn, hãy hoàn thành checklist:

- [ ] Đã chọn rõ nhánh MySQL LTS hoặc Innovation và ghi lại phiên bản đầy đủ.
- [ ] Server và client đều khởi động được; đã phân biệt phiên bản client với phiên bản Server.
- [ ] Đã chọn cách chạy phù hợp: cài trực tiếp, Docker Compose hoặc cloud.
- [ ] Máy còn đủ RAM, CPU và dung lượng SSD cho dữ liệu thực hành.
- [ ] Đã tạo database và tài khoản học riêng; không dùng root cho truy vấn thông thường.
- [ ] Đã xác nhận host, port, charset và collation.
- [ ] Nếu dùng Docker, dữ liệu được lưu trong volume và đã hiểu lệnh nào có thể xóa volume.
- [ ] Đã biết cách xem log, dừng, khởi động lại và backup dữ liệu.

Một môi trường được chuẩn bị tốt giúp kết quả bài tập có thể tái lập. Khi gặp khác biệt về cú pháp hoặc hiệu năng, hãy kiểm tra phiên bản Server, cấu hình và dữ liệu trước khi kết luận rằng câu lệnh hoặc cách thiết kế là sai.

## Tài liệu tham khảo chính thức

Các phiên bản và tag trong bài được đối chiếu tại ngày **19-11-2026**. Trước khi dựng môi trường mới, hãy kiểm tra lại trang tải xuống và release notes để biết bản vá mới nhất.

1. [MySQL 9.7 Reference Manual — MySQL Releases: Innovation and LTS](https://dev.mysql.com/doc/refman/9.7/en/mysql-releases.html): khác biệt giữa LTS và Innovation, chu kỳ hỗ trợ và cách đánh số phiên bản.
2. [MySQL 9.7 Reference Manual — Which MySQL Version and Distribution to Install](https://dev.mysql.com/doc/refman/9.7/en/which-version.html): lựa chọn nhánh phát hành và gói cài đặt.
3. [MySQL 9.7 Reference Manual — Installing MySQL](https://dev.mysql.com/doc/refman/9.7/en/installing.html): hướng dẫn cài đặt theo hệ điều hành và nền tảng được hỗ trợ.
4. [MySQL Community Server Downloads](https://dev.mysql.com/downloads/mysql/): tải Server và kiểm tra phiên bản đang được phân phối.
5. [Docker Official Image — mysql](https://hub.docker.com/_/mysql): tag image, biến môi trường, khởi tạo database, lưu trữ dữ liệu và ví dụ Docker Compose.
6. [MySQL Workbench Downloads](https://dev.mysql.com/downloads/workbench/): tải công cụ giao diện đồ họa và xem thông tin tương thích.

