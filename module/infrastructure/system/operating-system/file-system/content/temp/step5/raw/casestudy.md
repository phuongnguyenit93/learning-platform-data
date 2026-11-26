Một tiến trình mở /srv/app/config.yaml trước khi quản trị viên thay filesystem được mount tại /srv/app; lần open theo đường dẫn sau thay đổi thấy nội dung mới, còn file descriptor cũ vẫn trỏ tới đối tượng đã mở trước đó, khiến hai lần đọc cho kết quả khác nhau.
Một ứng dụng kiểm tra tồn tại của /data/reports/current.csv bằng đường dẫn tương đối; khi cron job chạy với working directory khác, ứng dụng báo thiếu tệp dù dữ liệu vẫn nằm đúng trên filesystem.
Một máy chủ có hàng triệu tệp nhỏ trong thư mục cache; thao tác liệt kê thư mục ngày càng chậm dù dung lượng đĩa còn trống, khiến nhóm SRE cần xem xét chi phí tra cứu dentry và cấu trúc thư mục.
Một tiến trình đọc cùng một đường dẫn nhiều lần nhưng kết quả thay đổi sau khi file được thay thế bằng rename; nhóm phát triển nhầm rằng inode và tên tệp là một định danh cố định nên không xử lý được hành vi file descriptor cũ.
Một quản trị viên xóa tệp cấu hình rồi tạo tệp mới cùng tên; tiến trình đang chạy vẫn đọc nội dung cũ qua file descriptor mở trước đó, gây nhầm lẫn khi kiểm tra đường dẫn trên shell.
Một dịch vụ ghi log xóa file đã rotate nhưng dung lượng filesystem không giảm; kiểm tra cho thấy tiến trình logger vẫn giữ file descriptor mở tới inode đã unlink, khiến dữ liệu chỉ được giải phóng sau khi đóng descriptor cuối cùng.
Một công cụ đồng bộ phát hiện hai đường dẫn có cùng nội dung và thay một tệp bằng hard link để tiết kiệm dung lượng; khi một ứng dụng chỉnh sửa tại chỗ, nội dung ở đường dẫn còn lại cũng thay đổi ngoài dự kiến.
Một nhóm phát hành ứng dụng dùng symbolic link current trỏ tới phiên bản mới; sau khi xóa thư mục phiên bản cũ, một số tiến trình còn giữ working directory hoặc đường dẫn con qua symlink và gặp lỗi truy cập.
Một script triển khai tạo symlink tương đối nhưng được gọi từ thư mục làm việc khác; liên kết trở thành dangling dù đường dẫn đích tồn tại ở vị trí mà người vận hành dự kiến.
Một ứng dụng tạo hàng trăm nghìn tệp nhỏ trong filesystem và chạm giới hạn inode dù df vẫn báo còn nhiều gigabyte trống; dịch vụ không thể tạo file mới và đội trực ban đầu nghi ngờ hết dung lượng block.
Một nhóm triển khai ứng dụng bằng tài khoản service nhưng thư mục dữ liệu được tạo bởi root với mode 755; ứng dụng đọc được file nhưng không tạo được file tạm, khiến thao tác cập nhật thất bại.
Một thư mục chia sẻ được cấp quyền group write nhưng người dùng trong nhóm không thể xóa tệp của nhau do sticky bit; nhóm hỗ trợ cần phân biệt quyền trên thư mục với quyền trên chính tệp.
Một thư mục upload có default ACL cho nhóm vận hành nhưng ứng dụng tạo file với mode giới hạn quyền group; ACL hiệu lực bị giới hạn theo mode và ACL mask, khiến người dùng trong nhóm không đọc được tài liệu như kỳ vọng.
Một ứng dụng cần truy cập thư mục dữ liệu qua nhiều thư mục cha; quyền đọc trên file đã đủ nhưng thiếu execute permission trên một thư mục trong đường dẫn nên open vẫn trả permission denied.
Một thư mục dự án dùng setgid bit để file mới kế thừa group chung; một quy trình triển khai thay mode của thư mục làm mất bit này và các file tạo sau đó thuộc nhóm mặc định của tài khoản chạy.
Một NFS export dùng root_squash nhưng đội backup chạy dưới root và mong giữ nguyên owner của file; sau khi restore, quyền sở hữu bị ánh xạ sang anonymous user và ứng dụng không truy cập được dữ liệu.
Một máy Linux có cùng đường dẫn /data nhưng container nhìn thấy filesystem khác do mount namespace; người vận hành kiểm tra mount ở host và tưởng volume đã được gắn vào container.
Một service mount bind thư mục cấu hình vào container ở chế độ read-write; ứng dụng trong container sửa file trên host ngoài dự kiến, gây thay đổi cấu hình cho các dịch vụ khác dùng chung thư mục.
Một hệ thống dùng mount propagation private cho thư mục chứa volume; mount con được tạo trong container không xuất hiện ở namespace host, khiến agent giám sát không nhìn thấy filesystem vừa gắn.
Một pod dùng emptyDir dạng tmpfs để lưu dữ liệu tạm nhưng ứng dụng ghi nhiều tệp lớn; bộ nhớ node bị tiêu thụ nhanh dù df của ổ đĩa persistent vẫn còn trống.
Một ứng dụng container dùng OverlayFS và ghi đè một file lớn từ image layer; copy-up tạo bản sao ở upper layer làm dung lượng tăng mạnh dù thay đổi logic chỉ là vài byte.
Một nhóm triển khai xóa file trong container image layer để giải phóng dung lượng; OverlayFS tạo whiteout ở upper layer nhưng dữ liệu gốc vẫn nằm trong lower layer, khiến kích thước image không giảm như kỳ vọng.
Một container ghi dữ liệu quan trọng vào writable layer của OverlayFS; khi pod bị thay thế, dữ liệu mất vì layer đó không phải volume bền vững, khiến đội phát triển cần phân biệt filesystem hợp nhất với storage persistent.
Một hệ thống NFS mount thư mục chia sẻ và giữ cache thuộc tính lâu; người dùng ở máy khác đổi quyền file nhưng ứng dụng đọc thấy metadata cũ, gây nhầm lẫn về thời điểm cập nhật và cache consistency.
Một client NFS giữ file handle tới tệp đã bị xóa hoặc thay thế trên server; lần đọc tiếp theo trả stale file handle và nhóm vận hành phải xác định quan hệ giữa inode phía client và đối tượng phía server.
Một ứng dụng nhiều máy cùng ghi vào file trên NFS nhưng dựa vào giả định khóa cục bộ; dữ liệu bị ghi đè do các tiến trình không phối hợp locking qua giao thức chia sẻ.
Một nhóm mount NFS với tùy chọn hard và ứng dụng chờ I/O vô thời hạn khi server mất kết nối; dịch vụ bị treo dù CPU thấp và health check không phân biệt được đang chờ filesystem.
Một hệ thống dùng mount option noatime để giảm ghi metadata; công cụ backup cũ dựa vào access time để quyết định file cần sao lưu và bỏ sót một số tệp được đọc gần đây.
Một ứng dụng mmap tệp cấu hình ở chế độ MAP_PRIVATE trong khi tiến trình khác cập nhật nội dung file; nhóm vận hành thấy mapping không phản ánh thay đổi như kỳ vọng và cần phân biệt page cache dùng chung với các trang copy-on-write riêng của mapping.
Một máy chủ có lượng dữ liệu ghi lớn và dirty pages tăng liên tục; write() trả nhanh nhưng writeback phía sau làm I/O dồn cục, khiến latency của các tiến trình khác tăng đột biến.
Một ứng dụng ghi dữ liệu giao dịch rồi gọi close() và trả thành công cho khách; sau khi mất điện, phần dữ liệu cuối không có trên đĩa vì close không bảo đảm đồng bộ bền vững như fsync.
Một nhóm ghi file tạm rồi rename thành file chính để cập nhật cấu hình nguyên tử; sau sự cố mất điện, tên file mới tồn tại nhưng nội dung hoặc directory entry chưa được bảo đảm bền vững vì thiếu đồng bộ thư mục theo yêu cầu.
Một dịch vụ dùng fdatasync để giảm chi phí ghi và cho rằng mọi metadata đều được đồng bộ; sau crash, nội dung cùng metadata cần thiết để truy xuất dữ liệu đã bền vững nhưng mtime hoặc directory entry của file mới vẫn cần cơ chế đồng bộ phù hợp.
Một database ghi WAL vào filesystem ext4 và giả định mọi write đã được flush khi syscall trả về; sau reboot, các transaction cuối bị mất vì ứng dụng không thực hiện chuỗi đồng bộ cần thiết.
Một máy chủ gặp sự cố nguồn điện khi filesystem đang có nhiều metadata update; journal replay giúp phục hồi cấu trúc nhưng không tự bảo đảm nội dung ứng dụng đã được fsync đúng thời điểm.
Một volume XFS báo lỗi metadata và được remount read-only; đội vận hành cố chạy thao tác ghi để sửa file nhưng cần đánh giá tình trạng filesystem và công cụ repair phù hợp trước khi tiếp tục.
Một phân vùng ext4 không mount được sau khi máy tắt đột ngột; nhóm trực muốn chạy fsck ngay khi volume còn được mount read-write, có nguy cơ làm tình trạng filesystem xấu hơn.
Một hệ thống XFS bị corruption sau lỗi storage; runbook nội bộ hướng dẫn dùng fsck chung cho mọi filesystem, trong khi XFS cần quy trình kiểm tra và sửa chữa riêng.
Một máy chủ báo df còn ít dung lượng nhưng du cộng các thư mục không khớp tổng block đã dùng; một phần dung lượng nằm trong file đã unlink nhưng còn mở và một phần do mount point che khuất.
Một thư mục chứa file lớn được tạo dạng sparse; ls hiển thị kích thước logic hàng trăm gigabyte trong khi du báo dung lượng block nhỏ, khiến nhóm backup nhầm rằng đã sao chép đủ dung lượng vật lý.
Một ứng dụng tạo sparse file để làm ảnh đĩa ảo nhưng công cụ copy không giữ hole và ghi toàn bộ vùng zero; bản sao chiếm đầy filesystem dù nội dung logic giống hệt nguồn.
Một filesystem chứa hàng triệu file rất nhỏ nhưng mỗi file vẫn tiêu thụ inode, metadata và phần cấp phát dữ liệu tối thiểu; dung lượng block dùng thực tế lớn hơn tổng kích thước logic mà nhóm ứng dụng cộng lại.
Một file lớn được mở rộng liên tục và filesystem cấp phát nhiều extent rời rạc; truy cập tuần tự chậm hơn sau thời gian dài dù thiết bị lưu trữ không thay đổi, khiến nhóm cần đánh giá fragmentation và layout.
Một volume Btrfs có snapshot giữ các block dùng chung; đội vận hành thấy file đã xóa nhưng dung lượng vẫn không giảm và cần xác định snapshot hoặc subvolume nào còn tham chiếu dữ liệu.
Một nhóm dùng reflink để nhân bản file dữ liệu lớn nhanh chóng; sau nhiều lần sửa các bản sao, copy-on-write tạo thêm extent và dung lượng thực tế tăng dần dù ban đầu các file dùng chung block.
Một filesystem có quota theo user và group; một ứng dụng hết quota của service account dù phân vùng còn trống, khiến lỗi ghi bị nhầm thành filesystem full.
Một nhóm thiết lập project quota cho thư mục upload nhưng file được chuyển bằng rename từ cây thư mục có project ID khác; thao tác bị từ chối hoặc số liệu quota không như dự kiến vì project ID không tự đổi theo đường dẫn mới.
Một filesystem dành reserved blocks cho root; ứng dụng chạy user thường hết dung lượng ghi trong khi df vẫn còn một phần dung lượng khả dụng dành cho quản trị, khiến đội trực cần phân biệt free và available blocks.
Một tiến trình mở hàng nghìn file nhưng không đóng descriptor; hệ thống báo too many open files dù filesystem còn đủ inode và block, khiến nhóm vận hành cần phân biệt giới hạn file descriptor với dung lượng lưu trữ.
Một nhóm backup sao chép thư mục database trong khi database vẫn đang ghi; bản sao chứa file dữ liệu và journal ở các thời điểm khác nhau nên không thể phục hồi nhất quán sau khi chuyển sang máy mới.
Một ứng dụng cần cập nhật đồng thời nhiều file cấu hình; rename từng file là nguyên tử riêng lẻ nhưng toàn bộ tập file không được cập nhật như một giao dịch, khiến tiến trình đọc thấy phiên bản pha trộn.
Một dịch vụ lưu file bằng cách ghi đè trực tiếp nội dung đang được nhiều reader mở; reader thấy file bị truncate trong lúc ghi và trả kết quả rỗng, trong khi phương án tạo file mới rồi rename chưa được áp dụng.
Một nhóm triển khai backup incremental dựa vào mtime nhưng đồng hồ hệ thống thay đổi sau đồng bộ NTP; một số file sửa gần đây có timestamp cũ hơn mốc backup và bị bỏ qua.
Một hệ thống cần lưu owner, ACL, xattrs và hard links khi backup; công cụ copy mặc định chỉ giữ nội dung và mode cơ bản nên restore không khôi phục được quyền truy cập và cấu trúc liên kết ban đầu.
Một volume mã hóa bằng fscrypt có tên file được bảo vệ theo policy thư mục; khi restore sang máy khác mà thiếu khóa và cấu hình policy, dữ liệu vẫn hiện diện trên block device nhưng không thể giải mã tên hoặc nội dung.
Một máy chủ sử dụng filesystem có checksum và phát hiện lỗi đọc dữ liệu; đội vận hành chỉ thấy I/O error ở ứng dụng nhưng chưa có quy trình scrub hoặc kiểm tra bản sao để xác định block hỏng.
Một hệ thống dùng snapshot storage để backup máy ảo nhưng snapshot được tạo trong khi ứng dụng đang ghi nhiều file liên quan; snapshot chỉ nhất quán ở mức crash và database cần quy trình quiesce hoặc phục hồi journal để đảm bảo tính nhất quán ứng dụng.
Một dịch vụ phụ thuộc vào mount network trong boot sequence nhưng systemd không có dependency phù hợp; ứng dụng khởi động trước khi mount sẵn sàng và tạo thư mục dữ liệu trên root filesystem.
Một nhóm nâng cấp kernel làm thay đổi module filesystem và volume không tự mount sau reboot; thiết bị block vẫn xuất hiện nhưng mount thất bại do filesystem driver hoặc cấu hình mount không tương thích.
Một máy chủ cần điều tra lỗi ghi chậm và nhóm chỉ dùng iostat của thiết bị; không có thông tin về process, filesystem, dirty pages và queue nên không phân biệt được ứng dụng ghi nhiều với writeback bị nghẽn.
Một filesystem gần đầy và ứng dụng ghi log không có rotation; khi log chiếm hết dung lượng, dịch vụ không thể tạo socket hoặc file trạng thái và gặp lỗi lan sang nhiều thành phần khác.
Một nhóm đặt logrotate copytruncate cho log đang được ứng dụng ghi với tốc độ cao; dữ liệu phát sinh giữa lúc copy và truncate bị mất, khiến bằng chứng sự cố không đầy đủ.
Một máy chủ có nhiều mount point và cảnh báo disk usage chỉ kiểm tra root filesystem; volume chứa database đầy trước nhưng không tạo alert, dẫn tới lỗi ghi dữ liệu dù dashboard host vẫn xanh.
Một ứng dụng dùng symlink để chuyển thư mục dữ liệu sang volume mới nhưng backup agent chỉ theo dõi đường dẫn cũ và không follow symlink; bản sao lưu không chứa dữ liệu đang hoạt động sau migration.
Một hệ thống cần xóa an toàn dữ liệu nhạy cảm trên SSD; nhóm vận hành dùng ghi đè nhiều lần lên file rồi cho rằng block đã bị xóa, trong khi wear leveling và copy-on-write có thể giữ bản cũ ở vị trí vật lý khác.
