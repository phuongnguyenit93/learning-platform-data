# Tạo môi trường Oracle cô lập bằng container hoặc máy ảo tự động

Một môi trường Oracle cô lập giúp lập trình viên và DBA thử nghiệm SQL, schema migration, JDBC, backup/restore, Data Pump, PL/SQL và các tình huống lỗi mà không ảnh hưởng database dùng chung. Khi môi trường được tạo tự động, nhóm có thể tái tạo cùng một phiên bản database, cùng cấu hình khởi tạo và cùng dữ liệu kiểm thử trên máy cá nhân, CI runner hoặc máy chủ lab.

Hai cách triển khai phổ biến:

- **Container:** chạy Oracle Database trong Docker hoặc Podman. Khởi tạo nhanh, ít tốn tài nguyên hơn VM và dễ gắn vào pipeline.
- **Máy ảo (VM):** tạo một guest OS riêng bằng VirtualBox, VMware, KVM hoặc nền tảng cloud. VM có kernel và hệ điều hành riêng, phù hợp khi cần kiểm thử OS, native library, network hoặc isolation mạnh hơn container.

Có thể kết hợp hai cách: tạo VM tự động bằng Vagrant/Packer, sau đó dùng Ansible để cài container runtime và chạy Oracle Database container bên trong VM. Cách kết hợp này tạo một lab có thể tái tạo và kiểm soát hạ tầng tương đối rõ.

## 1. Mục tiêu và phạm vi của môi trường cô lập

Một lab Oracle tốt cần đáp ứng:

- Không kết nối nhầm tới production.
- Có phiên bản database và service name được ghi nhận.
- Có dữ liệu thử nghiệm có thể tạo lại.
- Có volume lưu datafile tách biệt với vòng đời container.
- Có script khởi tạo schema và quyền theo nguyên tắc least privilege.
- Có health/readiness check trước khi chạy test.
- Có thể reset về trạng thái sạch hoặc restore snapshot.
- Có thể chạy tự động trên máy developer và CI.
- Có giới hạn CPU, RAM, storage và network.
- Không chứa dữ liệu thật hoặc secret production.

Mục tiêu của lab quyết định cách triển khai. Nếu chỉ cần kiểm thử SQL/JDBC, container Oracle Database Free thường đủ. Nếu cần thử kernel, systemd, Oracle Client native, ASM, nhiều node hoặc network routing phức tạp, VM hoặc lab chuyên dụng phù hợp hơn.

## 2. Container và VM khác nhau thế nào?

Container và VM đều cô lập môi trường ứng dụng, nhưng ranh giới kỹ thuật khác nhau.

~~~text
Container model

Host operating system and kernel
  |
  +-- Container runtime
        |
        +-- Oracle container
        |     +-- Oracle Database processes
        |     +-- Oracle data volume
        |
        +-- Test application container
              +-- JDBC driver
              +-- Integration tests

Virtual machine model

Physical host
  |
  +-- Hypervisor
        |
        +-- Guest OS
              +-- Oracle Database
              +-- Oracle data disks
              +-- Test tools
~~~

| Tiêu chí | Container | VM |
|---|---|---|
| Kernel | Dùng kernel của host | Có kernel guest riêng |
| Khởi động | Thường nhanh hơn | Thường chậm hơn |
| Tài nguyên | Thường nhẹ hơn | Thường cần nhiều RAM/disk hơn |
| Isolation | Namespace/cgroup và runtime boundary | Hypervisor boundary |
| Kiểm thử OS | Giới hạn bởi kernel host | Có thể dùng OS khác |
| Dữ liệu | Named volume/bind mount | Virtual disk |
| Tái tạo | Image và Compose | Box/template và provisioning |
| Phù hợp | SQL, JDBC, schema test, CI | OS/native/network, multi-node lab |
| Portability | Tốt nếu image hỗ trợ platform | Phụ thuộc hypervisor/box |

Container không phải VM thu nhỏ. Container chia sẻ kernel với host; không nên dùng container như ranh giới bảo mật duy nhất khi chạy mã không tin cậy. Với workload không tin cậy hoặc cần kiểm thử OS isolation, dùng VM hoặc môi trường sandbox được quản trị.

## 3. Chọn Oracle Database image

Chọn image phù hợp với mục đích và quyền sử dụng:

- Oracle Database Free phù hợp học tập, phát triển và kiểm thử trong giới hạn sản phẩm.
- Oracle Database Enterprise Edition hoặc Standard Edition cần tuân thủ quyền license và điều khoản sử dụng tương ứng.
- Oracle Container Registry có image do Oracle cung cấp; một số image/tag yêu cầu đăng nhập và chấp nhận điều khoản trước khi pull.
- Oracle GitHub repository docker-images chứa script hỗ trợ build một số image từ Oracle software distribution; cần tải phần mềm và tuân thủ license tương ứng.
- Image cộng đồng có thể tiện dụng, nhưng cần đánh giá nguồn gốc, maintainer, tag, Dockerfile, cập nhật bảo mật và điều khoản sử dụng trước khi dùng.

Không giả định việc chạy database trong container làm thay đổi license của database. Container là cách đóng gói và chạy phần mềm; quyền sử dụng vẫn phụ thuộc edition, deployment và hợp đồng.

### 3.1 Ưu tiên nguồn có thể kiểm chứng

Trước khi dùng image:

1. Xác định publisher và repository chính thức.
2. Đọc điều khoản và chấp nhận license nếu registry yêu cầu.
3. Chọn tag phiên bản cụ thể.
4. Ghi lại digest nếu pipeline cần tính tái lập cao.
5. Xem tài liệu về biến môi trường, volume và init scripts.
6. Kiểm tra kiến trúc CPU được hỗ trợ.
7. Đọc security advisories và lịch cập nhật image.

Tránh dùng tag latest trong pipeline quan trọng vì nội dung tag có thể thay đổi theo thời gian. Trong lab cá nhân có thể dùng latest để thử nhanh, nhưng cần ghi lại image ID và version thực tế.

### 3.2 Oracle Database Free

Ví dụ dưới đây dùng image Oracle Database Free từ Oracle Container Registry. Tên tag phải được chọn theo tài liệu registry tại thời điểm triển khai:

~~~text
container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Một số bản Oracle Database Free cung cấp CDB service FREE và PDB service FREEPDB1. Service name, tag, đường dẫn volume và script lifecycle cần được xác nhận theo tài liệu của image cụ thể.

Oracle Database Free có giới hạn tài nguyên và tính năng theo điều kiện sản phẩm. Không dùng kết quả lab Free để kết luận mọi hành vi/hiệu năng giống hệt Enterprise Edition.

## 4. Chuẩn bị Docker hoặc Podman

Máy chạy container cần:

- Docker Engine + Docker Compose plugin, hoặc Podman với Compose-compatible workflow.
- CPU architecture được image hỗ trợ.
- RAM và disk đủ cho database startup, workload và datafile.
- Port listener không bị chiếm.
- Quyền pull image từ registry.
- Thư mục/volume lưu dữ liệu bền vững.

Kiểm tra:

~~~bash
docker version
docker compose version
docker info
~~~

Với Podman:

~~~bash
podman version
podman info
~~~

Docker Desktop trên Windows/macOS thường chạy Linux containers thông qua một VM backend. Hãy phân biệt host port với container port khi cấu hình kết nối.

## 5. Đăng nhập registry và lấy image

Nếu Oracle Container Registry yêu cầu xác thực/đồng ý điều khoản, thực hiện bằng tài khoản được tổ chức cho phép:

~~~bash
docker login container-registry.oracle.com
docker pull container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Không lưu token registry trong source code hoặc file Compose. Dùng credential store của Docker, CI secret hoặc cơ chế secret manager phù hợp.

Kiểm tra image:

~~~bash
docker image inspect container-registry.oracle.com/database/free:<validated-version-tag>
docker image ls
~~~

Ghi lại repository/tag, image digest/ID, database release, ngày pull, nguồn registry và license/terms đã được chấp nhận.

## 6. Chạy container Oracle bằng docker run

Ví dụ khởi chạy Oracle Database Free:

~~~bash
docker volume create oracle-lab-data
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Trước khi chạy, đặt biến môi trường ORACLE_PWD trong terminal hoặc secret manager. Lệnh chỉ truyền biến môi trường hiện có vào container, không ghi password trực tiếp vào command text.

Ví dụ PowerShell:

~~~powershell
$env:ORACLE_PWD = "Use-a-local-lab-secret"
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Ví dụ Bash:

~~~bash
export ORACLE_PWD='Use-a-local-lab-secret'
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Password trong ví dụ chỉ là placeholder cho lab. Không dùng password production, không commit file chứa secret và không tái sử dụng mật khẩu này ở môi trường khác.

### 6.1 Vì sao publish port trên loopback?

Mapping 127.0.0.1:1521:1521 chỉ publish listener trên loopback host. Nó hạn chế các máy khác trong LAN truy cập trực tiếp vào database lab. Nếu cần truy cập từ máy khác, hãy thiết kế private network/firewall cụ thể thay vì publish database ra mọi interface.

### 6.2 Xem trạng thái và log

~~~bash
docker ps
docker logs -f oracle-lab
~~~

Database cần thời gian khởi tạo datafile và mở service. Container ở trạng thái running không đồng nghĩa database đã sẵn sàng nhận kết nối.

Chờ thông báo ready/success theo tài liệu image. Không chạy integration test ngay sau docker run mà chưa kiểm tra readiness.

### 6.3 Kết nối từ host

Với image cung cấp PDB service FREEPDB1, URL Thin thường có dạng:

~~~text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
~~~

Tài khoản và service thực tế phải theo cấu hình image. Kết nối bằng service name, không tự suy luận SID từ container name.

## 7. Dùng Docker Compose

Compose mô tả image, port, environment, volume và network trong một file để nhóm có thể tạo cùng môi trường bằng một lệnh.

Ví dụ cấu trúc thư mục:

~~~text
oracle-lab/
  compose.yaml
  .env
  .gitignore
  oracle-init/
    01-create-lab-user.sql
  tests/
    ...
~~~

### 7.1 File .env

~~~text
ORACLE_PWD=Use-a-local-lab-secret
~~~

Thêm .env vào .gitignore:

~~~text
.env
*.wallet
*.p12
*.jks
~~~

Không commit secret hoặc private key. Với CI, cấp ORACLE_PWD từ secret store thay vì lưu trong repository.

### 7.2 compose.yaml

~~~yaml
services:
  oracle:
    image: container-registry.oracle.com/database/free:<validated-version-tag>
    container_name: oracle-lab
    env_file:
      - .env
    ports:
      - "127.0.0.1:1521:1521"
    volumes:
      - oracle-data:/opt/oracle/oradata
      - ./oracle-init:/opt/oracle/scripts/setup:ro
    shm_size: 1g
    restart: unless-stopped

volumes:
  oracle-data:
~~~

Đường dẫn init script trong ví dụ là convention được một số Oracle database container image hỗ trợ. Hãy xác nhận chính xác thư mục setup/startup và hành vi chạy script theo tài liệu image đang pin. Không phải mọi image Oracle cộng đồng đều dùng cùng một đường dẫn.

### 7.3 Khởi chạy

~~~bash
docker compose config
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f oracle
~~~

docker compose config giúp xem cấu hình Compose đã được resolve. Không chia sẻ output nếu nó chứa giá trị secret.

### 7.4 Dừng và xóa

~~~bash
docker compose stop
docker compose start
docker compose down
~~~

down dừng và xóa container/network do Compose quản lý nhưng named volume thường vẫn được giữ.

Lệnh sau xóa cả volume được Compose quản lý:

~~~bash
docker compose down -v
~~~

Đây là thao tác xóa dữ liệu database lab. Chỉ dùng khi chắc chắn muốn reset toàn bộ datafile. Không chạy down -v trong thư mục Compose trỏ tới dữ liệu cần giữ.

## 8. Persistent volume và vòng đời dữ liệu

Container có thể bị xóa và tạo lại. Nếu datafile chỉ nằm trong writable layer của container, dữ liệu có thể mất khi container bị xóa.

Named volume giúp data sống độc lập với container:

~~~text
oracle-lab-data volume
        |
        v
/opt/oracle/oradata inside container
        |
        v
Oracle datafiles, control files, redo files
~~~

### 8.1 Named volume

~~~bash
docker volume create oracle-lab-data
docker volume inspect oracle-lab-data
~~~

Named volume phù hợp cho lab local và CI có nhu cầu giữ dữ liệu giữa các lần restart.

### 8.2 Bind mount

Có thể mount thư mục host:

~~~yaml
volumes:
  - ./data/oradata:/opt/oracle/oradata
~~~

Bind mount giúp nhìn thấy file ở host nhưng cần xử lý permission, filesystem performance, SELinux labels và khác biệt Windows/macOS/Linux. Với database file, named volume thường ít vấn đề hơn.

### 8.3 Restart khác reset

- Restart container: dừng và chạy lại process, giữ volume.
- Recreate container: tạo container mới, giữ named volume nếu không xóa.
- Reset database: xóa volume hoặc dùng quy trình recreate database.
- Restore snapshot: khôi phục volume/backup về một trạng thái đã lưu.

Không dùng restart như cách xóa dữ liệu test.

### 8.4 Backup volume

Volume không tự là backup. Có thể backup database bằng RMAN hoặc snapshot storage nhất quán theo quy trình. Copy trực tiếp datafile đang mở bằng file copy thông thường không đảm bảo backup nhất quán.

## 9. Khởi tạo schema tự động

Một lab có thể tự tạo user/schema và object sau khi database được tạo lần đầu. Dùng script init được version control, nhưng không đưa password thật vào script.

Ví dụ SQL:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE

ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE USER lab_app IDENTIFIED BY "ReplaceWithLabSecret";

GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE
TO lab_app;

ALTER USER lab_app QUOTA 500M ON USERS;

EXIT
~~~

Đây là ví dụ cho image/service có PDB FREEPDB1 và script chạy với quyền đủ cao. Tên PDB, tablespace, script execution context và cú pháp password phải khớp image/release.

Không cấp DBA, CREATE ANY TABLE hoặc quyền hệ thống rộng cho user ứng dụng chỉ để test CRUD.

### 9.1 Setup scripts và startup scripts

Một số image hỗ trợ hai loại thư mục:

- Setup scripts: chạy trong quá trình database khởi tạo lần đầu.
- Startup scripts: chạy mỗi lần database container khởi động.

Hành vi này khác nhau theo image. Nếu setup script chỉ chạy khi tạo database lần đầu, sửa file sau đó không làm script chạy lại trên volume đã tồn tại.

Vì vậy:

- Dùng setup script cho bootstrap ban đầu.
- Dùng migration tool hoặc automation riêng cho thay đổi schema về sau.
- Không đặt lệnh CREATE USER không idempotent trong startup script chạy mỗi lần.
- Log và kiểm tra exit code của init script.

### 9.2 Idempotent initialization

Script idempotent có thể chạy nhiều lần mà không tạo trạng thái lỗi hoặc dữ liệu trùng. SQL DDL của Oracle không phải lệnh nào cũng hỗ trợ IF NOT EXISTS ở mọi release; có thể dùng PL/SQL kiểm tra metadata trước khi tạo hoặc quản lý bằng migration tool.

Không bắt lỗi rồi bỏ qua mọi exception. Chỉ xử lý lỗi cụ thể đã dự kiến, còn lỗi khác phải làm job thất bại để CI không báo xanh giả.

## 10. Readiness check

Container running chỉ cho biết process chính chưa thoát. Oracle có thể vẫn đang:

- Tạo database.
- Khôi phục instance.
- Mở PDB.
- Chạy init script.
- Đăng ký service với listener.

Ứng dụng phải đợi database nhận được kết nối và query thành công.

### 10.1 Kiểm tra log

~~~bash
docker logs oracle-lab
~~~

Đọc thông báo ready cụ thể của image và version. Không phụ thuộc một chuỗi log nếu image thay đổi; readiness nên kiểm tra được kết nối thực tế.

### 10.2 Probe bằng SQL

Khi SQL*Plus có trong image:

~~~bash
docker exec -it oracle-lab bash
sqlplus -L system@//localhost:1521/FREEPDB1
~~~

Sau khi xác thực, chạy:

~~~sql
SELECT 1 FROM dual;
SELECT sys_context('USERENV', 'CON_NAME') AS con_name FROM dual;
~~~

Không truyền password vào câu lệnh shell nếu có thể tránh; dùng prompt hoặc secret mechanism.

### 10.3 Retry trong integration test

Test runner nên retry kết nối trong một khoảng giới hạn:

~~~java
long deadline = System.nanoTime() + Duration.ofMinutes(5).toNanos();
SQLException lastError = null;

while (System.nanoTime() < deadline) {
    try (Connection connection = dataSource.getConnection();
         Statement statement = connection.createStatement();
         ResultSet result = statement.executeQuery("SELECT 1 FROM dual")) {
        if (result.next() && result.getInt(1) == 1) {
            return;
        }
    } catch (SQLException e) {
        lastError = e;
        Thread.sleep(2000);
    }
}

throw new IllegalStateException("Oracle did not become ready", lastError);
~~~

Đây là pseudocode Java cần đặt trong method phù hợp và khai báo InterruptedException/exception handling. Production test nên phân biệt lỗi tạm thời do startup với lỗi cấu hình như sai password hoặc sai service; không retry vô hạn.

## 11. Kết nối từ test container và từ host

Hai đường kết nối khác nhau:

| Vị trí client | Host trong JDBC URL |
|---|---|
| Chạy trên host | localhost hoặc 127.0.0.1 |
| Chạy trong cùng Compose network | Tên service, ví dụ oracle |
| Chạy trong VM | IP/hostname private của VM |
| Chạy từ máy khác | Private DNS/IP được firewall cho phép |

Ví dụ từ host:

~~~text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
~~~

Ví dụ từ application container trong cùng Compose network:

~~~text
jdbc:oracle:thin:@//oracle:1521/FREEPDB1
~~~

Trong container, localhost trỏ về chính container đó, không phải Oracle container khác. Dùng service DNS của Compose network.

## 12. Tạo môi trường bằng Podman

Podman cung cấp workflow tương tự Docker cho nhiều use case:

~~~bash
podman pull container-registry.oracle.com/database/free:<validated-version-tag>
podman volume create oracle-lab-data
podman run -d --name oracle-lab -p 127.0.0.1:1521:1521 --env ORACLE_PWD -v oracle-lab-data:/opt/oracle/oradata container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Kiểm tra:

~~~bash
podman ps
podman logs -f oracle-lab
podman volume inspect oracle-lab-data
~~~

Podman rootless có thể có khác biệt về port binding, volume permission, cgroup và network. Xác nhận các giới hạn của môi trường host và image. Không giả định mọi Docker Compose feature hoạt động giống hệt với mọi phiên bản Podman.

## 13. Tạo VM tự động bằng Vagrant

VM phù hợp khi cần một guest OS độc lập. Vagrant giúp khai báo VM bằng file cấu hình và tái tạo VM bằng lệnh.

Một cấu trúc thư mục:

~~~text
oracle-vm-lab/
  Vagrantfile
  provision/
    site.yml
    files/
      compose.yaml
  inventory/
    ...
~~~

### 13.1 Vagrantfile

~~~ruby
Vagrant.configure("2") do |config|
  config.vm.box = ENV.fetch("ORACLE_LAB_BOX")
  config.vm.hostname = "oracle-lab"

  config.vm.network "private_network",
    ip: "192.168.56.20"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = 8192
    vb.cpus = 4
  end

  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "provision/site.yml"
  end
end
~~~

ORACLE_LAB_BOX là box đã được tổ chức kiểm tra và đăng ký trong Vagrant. Không dùng box không rõ nguồn gốc chứa sẵn database hoặc password.

RAM 8 GB và 4 CPU chỉ là giá trị ví dụ. Chọn theo Oracle release, memory target, host capacity và workload.

### 13.2 Khởi tạo VM

~~~bash
vagrant up
vagrant status
vagrant ssh
~~~

### 13.3 Dừng, snapshot và hủy VM

~~~bash
vagrant halt
vagrant snapshot save clean-baseline
vagrant snapshot restore clean-baseline
vagrant destroy
~~~

Snapshot là trạng thái của VM theo hypervisor/Vagrant. Cần hiểu snapshot có bao gồm disk và memory hay không, và không dùng snapshot đang chạy như một bản backup Oracle được chứng nhận.

## 14. Provision VM bằng Ansible

Ansible giúp cài package, tạo thư mục, cấu hình runtime, copy Compose file và khởi chạy container. Ví dụ playbook khái quát:

~~~yaml
---
- name: Provision Oracle lab host
  hosts: all
  become: true

  vars:
    lab_dir: /opt/oracle-lab

  tasks:
    - name: Create lab directory
      ansible.builtin.file:
        path: "{{ lab_dir }}"
        state: directory
        owner: root
        group: root
        mode: "0750"

    - name: Copy Compose definition
      ansible.builtin.copy:
        src: files/compose.yaml
        dest: "{{ lab_dir }}/compose.yaml"
        owner: root
        group: root
        mode: "0640"

    - name: Start Oracle lab
      ansible.builtin.command:
        cmd: docker compose up -d
        chdir: "{{ lab_dir }}"
      register: compose_result
      changed_when: "'Started' in compose_result.stdout or 'Created' in compose_result.stdout"
~~~

Playbook chỉ minh họa bước triển khai Compose. Cài Docker/Podman, đăng nhập registry, cung cấp .env và quản lý secret cần được bổ sung theo distro, collection và chuẩn bảo mật của tổ chức.

### 14.1 Ansible Vault

Không đặt database password dạng plaintext trong vars file hoặc repository. Dùng Ansible Vault hoặc secret manager để cấp secret. Bật no_log cho task có thể in credential ra stdout.

### 14.2 Idempotency

Ansible module chuyên dụng thường tốt hơn command tùy tiện vì module có thể xác định trạng thái trước/sau. Nếu dùng command, phải thiết kế changed_when, creates/removes và kiểm tra trạng thái để tránh chạy lại thao tác không cần thiết.

## 15. Cài Oracle Database trực tiếp trong VM

Nếu cần kiểm thử OS-level hoặc cấu hình Oracle Client/server native, có thể cài Oracle Database trực tiếp trong guest OS thay vì chạy container.

Các bước tổng quát:

1. Chọn Oracle Linux/OS được Oracle Database release hỗ trợ.
2. Cấp CPU, RAM, disk và filesystem.
3. Cài package/prerequisite theo installation guide.
4. Tải Oracle Database software từ nguồn được cấp phép.
5. Tạo response file đã được kiểm tra.
6. Cài software bằng silent installer.
7. Chạy root scripts theo thứ tự Oracle yêu cầu.
8. Tạo database/PDB bằng DBCA silent mode hoặc template được quản trị.
9. Cấu hình listener và service.
10. Cấu hình startup/shutdown và monitoring.
11. Chạy smoke test và lưu baseline.

### 15.1 Silent installation

Oracle Universal Installer và DBCA hỗ trợ chế độ silent với response file hoặc command-line parameters theo release. Tên response file, tham số và prerequisite khác nhau giữa phiên bản.

Không copy một response file 19c vào 23ai hoặc release khác mà không kiểm tra tài liệu. Lưu response file trong kho cấu hình bảo mật và không commit password.

### 15.2 DBCA

DBCA có thể tạo database và PDB theo cấu hình. Khi tự động hóa:

- Chọn DB name/SID duy nhất trong lab.
- Chọn character set phù hợp ứng dụng.
- Chọn CDB/PDB topology.
- Đặt memory target theo RAM VM.
- Chọn filesystem/ASM theo mục tiêu test.
- Đặt listener/service rõ ràng.
- Tạo user lab least privilege.
- Bật ARCHIVELOG nếu bài test cần backup/recovery.

### 15.3 Khi nào không cần cài native database trong VM?

Nếu chỉ cần database để chạy integration test, container thường ít bước hơn. VM native install phù hợp hơn khi bài test phụ thuộc OS packages, kernel, ASM, service management hoặc Oracle Client/Database native setup.

## 16. Tự động hóa bằng Packer

Packer có thể tạo machine image/box đã được chuẩn bị sẵn. Pipeline có thể:

1. Lấy base image đã phê duyệt.
2. Tạo builder VM tạm.
3. Cài OS updates và prerequisite.
4. Cài container runtime hoặc Oracle software theo license.
5. Cấu hình monitoring và hardening.
6. Xóa cache/secret tạm.
7. Chạy smoke tests.
8. Xuất artifact VM image.

Không bake password, private key, registry token hoặc dữ liệu cá nhân vào machine image. Dùng provisioning-time secret và rotate sau khi build nếu có credential tạm.

## 17. Tạo database test schema có thể tái lập

Một lab không chỉ cần database process. Nó cần schema và dataset có thể tạo lại cùng kết quả.

Nên quản lý:

- DDL schema.
- Reference data.
- Test fixtures.
- Stored procedure/package.
- Grants và roles.
- Database parameters cần cho test.
- Migration version.

Các công cụ migration phổ biến như Flyway hoặc Liquibase có thể áp dụng DDL theo version. Test setup nên chạy migration từ đầu trên database rỗng để phát hiện dependency ẩn.

### 17.1 Không dùng production dump làm fixture mặc định

Dữ liệu production có thể chứa thông tin cá nhân, tài chính hoặc bí mật thương mại. Dùng synthetic data hoặc dữ liệu đã mask theo quy trình được phê duyệt.

### 17.2 Deterministic test data

Để test có thể lặp lại:

- Dùng seed cố định cho random data.
- Dùng ngày giờ cố định hoặc Clock injection.
- Không phụ thuộc thứ tự SELECT nếu thiếu ORDER BY.
- Tạo key test có namespace rõ.
- Dọn dữ liệu sau test bằng transaction/schema reset.
- Không dùng chung một schema cho test chạy song song nếu có thể xung đột.

## 18. Cô lập test và tránh xung đột

Có nhiều mức isolation:

### 18.1 Một database, nhiều schema

Ưu điểm: nhẹ và nhanh. Nhược điểm: resource và instance parameters dùng chung, schema có thể ảnh hưởng nhau qua shared objects/locks.

### 18.2 Một database container cho mỗi test suite

Ưu điểm: dễ reset toàn database và giảm xung đột. Nhược điểm: tốn RAM/CPU/disk khi chạy nhiều suite.

### 18.3 Một container cho mỗi CI job

Ưu điểm: job độc lập, cleanup rõ. Phù hợp integration test nếu host có đủ tài nguyên.

### 18.4 Một VM cho mỗi test group

Ưu điểm: isolation OS/network tốt hơn. Nhược điểm: khởi động chậm và tốn tài nguyên.

### 18.5 Chọn isolation theo mục tiêu

| Nhu cầu | Mức isolation phù hợp |
|---|---|
| Unit test không cần Oracle | Mock/fake repository hoặc test double |
| SQL integration test nhỏ | Một Oracle container cho test suite |
| Migration test độc lập | Container mới cho mỗi CI job |
| Kiểm tra Oracle Client native | VM hoặc runner có client được pin |
| Kiểm thử RAC/Data Guard | Lab chuyên dụng nhiều node |
| Chạy mã không tin cậy | VM/sandbox được quản trị |

## 19. Tích hợp Oracle container vào CI

Pipeline điển hình:

~~~text
Checkout source
     |
     v
Pull pinned Oracle image
     |
     v
Start isolated database
     |
     v
Wait for database readiness
     |
     v
Create test user and schema
     |
     v
Run migrations
     |
     v
Run integration tests
     |
     v
Collect logs and reports
     |
     v
Stop and remove container/volume
~~~

### 19.1 Các bước pipeline

1. Lấy image theo tag/digest đã pin.
2. Cấp password từ CI secret.
3. Tạo volume/job network riêng.
4. Khởi chạy Oracle.
5. Retry tới khi SQL query thành công.
6. Tạo schema và load fixture.
7. Chạy integration test.
8. Lưu test report và database log khi thất bại.
9. Dừng container.
10. Xóa volume ephemeral của job.

### 19.2 Tên resource riêng cho mỗi job

Dùng tên container, volume và network có build ID hoặc job ID để tránh hai pipeline cùng tác động một database:

~~~text
oracle-ci-<job-id>
oracle-data-<job-id>
oracle-net-<job-id>
~~~

Tên này là quy ước minh họa. CI runner cần cleanup cả khi job timeout hoặc bị cancel.

### 19.3 Không dùng volume chung giữa job song song

Hai job không được mount cùng datafile directory của một database instance độc lập. Việc cùng truy cập Oracle datafiles từ nhiều container/instance không phải cách chia sẻ database.

Mỗi instance cần storage riêng, trừ kiến trúc cluster được Oracle hỗ trợ và cấu hình đúng.

### 19.4 Thu thập log trước cleanup

Nếu test fail:

- Lấy application test report.
- Lấy Oracle alert/diagnostic log phù hợp.
- Lấy container logs.
- Ghi image tag/digest.
- Ghi JDBC driver version.
- Ghi database version và service.

Sau đó mới cleanup resource ephemeral. Không lưu password hoặc dữ liệu nhạy cảm trong artifact CI.

## 20. Reset database giữa các test

Có một số chiến lược:

- Tạo container và volume mới cho mỗi suite.
- Tạo schema mới cho mỗi suite.
- Dùng migration rollback/cleanup.
- Restore snapshot baseline đã được tạo nhất quán.

### 20.1 Xóa volume và tạo lại

~~~bash
docker compose down -v
docker compose up -d
~~~

Cách này khởi tạo database mới từ đầu theo image và setup scripts. Nó xóa dữ liệu trong named volume của project.

### 20.2 Reset schema

Có thể drop/recreate schema test bằng automation có quyền phù hợp. Cần bảo đảm không nhắm nhầm schema hoặc database dùng chung.

### 20.3 Snapshot baseline

VM snapshot hoặc storage snapshot có thể rút ngắn thời gian reset. Nhưng database phải ở trạng thái snapshot được hỗ trợ; snapshot crash-consistent không luôn tương đương backup Oracle application-consistent.

Nếu cần bảo đảm, dùng RMAN duplicate/restore hoặc cơ chế snapshot được Oracle/storage vendor hỗ trợ và kiểm thử restore.

## 21. Quản lý resource

Oracle Database cần RAM và shared memory đáng kể. Nếu cấp quá ít, database có thể khởi tạo chậm, không mở service hoặc bị OOM kill.

Theo dõi:

- RAM host và container.
- CPU utilization.
- Disk free space.
- Volume growth.
- Shared memory.
- Container restart count.
- Database alert log.

### 21.1 Memory

Đặt memory limit phù hợp với database SGA/PGA và overhead OS. Đừng đặt container memory limit thấp hơn tổng nhu cầu database.

### 21.2 CPU

CPU quota quá thấp có thể làm startup và test chậm. Dùng giới hạn phù hợp để một lab không chiếm toàn bộ host.

### 21.3 Storage

Theo dõi volume và filesystem. Oracle datafile có thể autoextend, do đó cần giới hạn dung lượng và cảnh báo trước khi host hết disk.

### 21.4 Shared memory

Một số Oracle container cần shm-size đủ lớn. Giá trị phải theo hướng dẫn image/database release và cấu hình memory.

## 22. Bảo mật lab

Lab vẫn là database server có listener và credential. Các nguyên tắc:

- Chỉ publish listener lên loopback nếu chỉ dùng local.
- Không dùng password production.
- Không mở port database ra Internet.
- Dùng user lab có quyền tối thiểu.
- Không chạy ứng dụng với SYS/SYSTEM.
- Không mount Docker socket vào container ứng dụng nếu không cần.
- Không chạy image không rõ nguồn gốc.
- Pin image version/digest.
- Cập nhật image và host runtime.
- Không lưu dữ liệu production chưa mask.
- Giới hạn quyền đọc volume và wallet.
- Dọn secret sau khi test.

Container có thể được cấu hình privileged hoặc mount host path rộng; tránh các quyền này cho lab thông thường.

## 23. Môi trường nhiều database/service

Có thể chạy nhiều container cho các mục tiêu khác nhau:

- Oracle Database Free cho SQL/PLSQL lab.
- Database release khác để kiểm tra compatibility.
- Một container làm source, một container làm target migration.
- Một database dành cho integration test và một cho performance test.

Mỗi instance cần:

- Container name riêng.
- Host port riêng nếu publish.
- Volume riêng.
- Service name được ghi nhận.
- CPU/RAM budget.
- Network isolation.

Không chạy hai database instance độc lập cùng mount một Oracle data directory.

## 24. Kiểm thử JDBC trong lab

Sau khi Oracle ready, chạy một smoke test:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps =
         connection.prepareStatement("SELECT sys_context('USERENV','SERVICE_NAME') FROM dual");
     ResultSet rs = ps.executeQuery()) {

    if (!rs.next()) {
        throw new IllegalStateException("Oracle returned no row");
    }

    System.out.println("Connected service: " + rs.getString(1));
}
~~~

Smoke test nên kiểm tra:

- Kết nối đúng database/service.
- User đúng schema.
- Có thể chạy SELECT.
- Có thể INSERT/UPDATE/ROLLBACK trên fixture.
- Character set và datatype.
- Migration chạy được.
- Pool trả connection đúng.

Không chỉ kiểm tra ping port 1521; port mở không chứng minh database đã sẵn sàng.

## 25. Kiểm thử migration và tương thích phiên bản

Một môi trường cô lập hữu ích để kiểm tra:

- Flyway/Liquibase migrations.
- DDL trên schema mới.
- JDBC driver mới.
- Database upgrade compatibility.
- Data Pump import/export.
- RMAN backup/restore trong lab phù hợp.
- Flashback features theo edition/version.
- Stored procedure/package compile.
- Constraint và index rebuild.

Đối với test version compatibility, chạy database version mà production thực sự dùng và version mục tiêu. Không chỉ dùng image latest.

## 26. Troubleshooting container

### Container thoát ngay sau khi start

Kiểm tra:

- Image pull thành công?
- Registry terms đã được chấp nhận?
- Architecture có được hỗ trợ?
- ORACLE_PWD có đáp ứng yêu cầu?
- RAM/shared memory đủ?
- Volume permission đúng?
- Log có lỗi initialization?

### Container running nhưng không kết nối được

Kiểm tra:

- Database startup đã hoàn tất?
- Listener đang mở?
- PDB/service đã open?
- Host port mapping đúng?
- Firewall/local security software?
- URL dùng đúng service?

### Data mất sau recreate

Kiểm tra:

- Named volume có được mount?
- Có vô tình dùng docker compose down -v?
- Image có thay đổi mount path?
- Datafile directory có đúng?

### Permission denied trên volume

Kiểm tra UID/GID của user chạy Oracle trong image, filesystem và SELinux. Không dùng chmod 777 làm cách sửa mặc định.

### Out of disk

Kiểm tra Docker volume, filesystem, autoextend, log và dump file. Xóa đúng dữ liệu lab theo quy trình; không xóa file database đang mở bằng lệnh OS.

## 27. Troubleshooting VM

### VM không boot

Kiểm tra:

- Hypervisor đã bật virtualization support?
- Nested virtualization có cần không?
- RAM/CPU host đủ?
- Box có đúng provider?
- Disk còn chỗ?

### Provisioning thất bại

Kiểm tra Ansible inventory, SSH, become privilege, package repository, network và log task. Chạy lại playbook sau khi sửa lỗi idempotency.

### Database không khởi động

Kiểm tra alert log, filesystem, listener, environment variables, ownership và database service. Không xóa datafile để ép DBCA chạy lại.

### VM snapshot không restore được

Kiểm tra hypervisor version, snapshot chain và disk capacity. Giữ backup độc lập nếu dữ liệu quan trọng; snapshot không phải phương án backup duy nhất.

## 28. Lựa chọn container hay VM

| Tiêu chí quyết định | Container | VM |
|---|---|---|
| Khởi tạo nhanh cho SQL lab | Rất phù hợp | Có thể quá nặng |
| Integration test trong CI | Rất phù hợp | Phù hợp nhưng chậm hơn |
| Kiểm tra Oracle JDBC Thin | Phù hợp | Phù hợp |
| Kiểm tra JDBC OCI native client | Có thể, cần native libs | Phù hợp |
| Kiểm tra OS package/systemd | Giới hạn | Phù hợp |
| Kiểm thử network nhiều subnet | Hạn chế hơn | Linh hoạt hơn |
| RAC/Data Guard multi-node | Cần thiết kế chuyên biệt | Lab VM chuyên dụng |
| Chạy mã không tin cậy | Không dùng làm boundary duy nhất | Phù hợp hơn nếu hardening đúng |
| Tài nguyên host hạn chế | Thường nhẹ hơn | Thường nặng hơn |
| Tái tạo hạ tầng | Compose/image | Packer/Vagrant/Ansible |

Đề xuất:

- Học SQL, PL/SQL, JDBC và schema migration: container Oracle Database Free.
- Kiểm tra native Oracle Client/OCI: VM hoặc container image có native client được kiểm soát.
- Kiểm tra OS và network: VM.
- CI integration test: container ephemeral.
- RAC/Data Guard: lab nhiều node chuyên dụng, không giả lập bằng một container đơn.

## 29. Mẫu workflow tự động hoàn chỉnh

Một workflow local:

~~~text
1. Clone repository lab
2. Kiểm tra Docker/Podman
3. Pull pinned image
4. Load secret từ local secret store
5. docker compose up -d
6. Wait for SQL readiness
7. Run setup/migrations
8. Run tests
9. Save logs/reports
10. Stop container
11. Keep or remove volume theo mục tiêu
~~~

Một workflow CI:

~~~text
1. Allocate isolated runner/job ID
2. Authenticate to approved registry
3. Start Oracle container with ephemeral volume
4. Wait for service and PDB
5. Create least-privilege test schema
6. Run migration and integration tests
7. Collect logs on failure
8. Publish test reports
9. Remove container, network and ephemeral volume
10. Verify cleanup
~~~

Một workflow VM:

~~~text
1. Select approved base box
2. vagrant up
3. Ansible provision OS and runtime
4. Deploy Oracle container or install database
5. Wait for readiness
6. Run test suite
7. Capture diagnostics
8. Snapshot clean baseline or destroy VM
~~~

## 30. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng tag latest trong CI | Kết quả thay đổi theo image update | Pin version tag/digest |
| Dùng image không rõ nguồn | Rủi ro supply chain và license | Chọn publisher/repository được phê duyệt |
| Nghĩ container đồng nghĩa free license | Vi phạm điều khoản | Kiểm tra edition và entitlement |
| Không mount persistent volume | Mất dữ liệu khi xóa container | Dùng named volume |
| Chạy test ngay sau docker run | Database chưa ready | SQL readiness probe và retry giới hạn |
| Publish 1521 ra mọi interface | Mở database lab cho LAN | Bind loopback hoặc private network |
| Dùng localhost từ app container | Kết nối nhầm chính container app | Dùng service DNS |
| Dùng chung volume cho nhiều instance | Hỏng database files | Mỗi instance một storage riêng |
| Commit .env/password | Lộ credential | Secret manager và .gitignore |
| Dùng SYS cho ứng dụng test | Quyền quá rộng | Tạo schema user riêng |
| Nghĩ setup script chạy mỗi lần restart | Schema không được cập nhật | Hiểu lifecycle image, dùng migration |
| Reset bằng restart | Dữ liệu cũ vẫn còn | Recreate volume/schema có chủ ý |
| Dùng down -v không kiểm tra | Xóa database volume | Xác nhận project/volume trước |
| Dùng container làm boundary cho mã không tin cậy | Rủi ro host kernel/runtime | Dùng VM/sandbox |
| Không giới hạn RAM/disk | Host bị cạn tài nguyên | Budget và monitoring |
| Dùng production dump chưa mask | Rò rỉ dữ liệu | Synthetic/masked fixtures |
| Chỉ test một version | Bỏ sót tương thích | Pin và chạy matrix version |
| Không cleanup CI job | Tích tụ volume/container | Cleanup cả khi fail/cancel |

## 31. Bài thực hành tự kiểm tra

Thực hiện trên máy cá nhân hoặc runner được phép, dùng dữ liệu giả.

### Bài 1 — Pull Oracle Database Free

Đăng nhập registry nếu cần, chọn tag cụ thể và ghi lại image digest.

### Bài 2 — Chạy container

Tạo named volume, publish port loopback, cung cấp ORACLE_PWD từ secret và khởi chạy database.

### Bài 3 — Kiểm tra readiness

Theo dõi log và chạy SELECT 1 FROM dual qua service PDB.

### Bài 4 — Kết nối JDBC

Dùng Thin driver, service name của PDB và user lab. Ghi driver/database version.

### Bài 5 — Khởi tạo schema

Mount SQL setup script để tạo user và schema fixture. Xác nhận script chỉ chạy theo lifecycle được image hỗ trợ.

### Bài 6 — Persistent volume

Restart và recreate container, xác nhận dữ liệu còn. Sau đó trong lab riêng chạy down -v và xác nhận database được tạo mới.

### Bài 7 — Compose network

Chạy test app container cùng network và kết nối qua hostname service oracle.

### Bài 8 — Vagrant

Tạo VM từ box đã phê duyệt, cấp RAM/CPU và private network.

### Bài 9 — Ansible

Provision runtime và triển khai Compose file bằng playbook có thể chạy lặp.

### Bài 10 — CI cleanup

Mô phỏng test pass và test fail; xác nhận log được lưu trước khi container/volume ephemeral bị xóa.

### Bài 11 — Resource limit

Đo RAM/CPU/disk trong lúc database khởi động và chạy test. Thử giới hạn trong lab và quan sát ảnh hưởng.

### Bài 12 — So sánh container/VM

Chạy cùng một integration suite trên container và VM. So sánh startup time, test duration, tài nguyên và độ phức tạp vận hành.

## 32. Checklist trước khi chia sẻ lab cho nhóm

**Nguồn và version**

- Image/box đến từ nguồn được phê duyệt?
- Tag/digest được pin?
- Edition và license terms đã rõ?
- Oracle release và service name đã ghi?

**Isolation**

- Database không trỏ tới production?
- Port chỉ mở trong phạm vi cần thiết?
- Volume và network riêng?
- CI job có resource name riêng?

**Dữ liệu và secret**

- Chỉ dùng dữ liệu synthetic/masked?
- Password lấy từ secret store?
- .env, wallet và private key không commit?
- User ứng dụng có quyền tối thiểu?

**Tái lập**

- Compose/Vagrant/Ansible nằm trong repository?
- Init scripts và migrations có version?
- Readiness check chạy trước test?
- Có thể reset về trạng thái sạch?

**Vận hành**

- RAM/CPU/disk có giới hạn?
- Log được thu thập?
- CI cleanup cả khi thất bại?
- Có hướng dẫn giữ hoặc xóa volume?
- Có người sở hữu cập nhật image và dependency?

## 33. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Container | Cô lập process nhưng dùng kernel host |
| VM | Guest OS/kernel riêng chạy trên hypervisor |
| Oracle Database Free | Phù hợp lab trong giới hạn sản phẩm |
| Oracle Container Registry | Nguồn image Oracle, có thể yêu cầu login/accept terms |
| Image tag/digest | Xác định phiên bản image cần tái tạo |
| Docker Compose | Khai báo service, port, volume và network |
| Named volume | Giữ data độc lập với container |
| Bind mount | Gắn thư mục host, cần xử lý permission |
| Init/setup script | Bootstrap database theo lifecycle của image |
| Readiness check | Xác nhận SQL/service sẵn sàng |
| FREEPDB1 | Ví dụ PDB service trên một số image Oracle Free |
| Vagrant | Tạo/quản lý VM bằng cấu hình |
| Ansible | Provision OS và triển khai cấu hình lặp lại |
| Packer | Tạo machine image/box tự động |
| Secret manager | Cấp credential mà không commit secret |
| Ephemeral CI volume | Data storage chỉ tồn tại trong một job |
| Snapshot | Mốc trạng thái; không tự thay thế backup database |
| Synthetic data | Dữ liệu giả an toàn cho kiểm thử |
| Cleanup | Xóa đúng container/network/volume sau test |

Để tạo lab Oracle có thể tái lập, hãy pin image hoặc VM box, quản lý cấu hình bằng Compose/Vagrant/Ansible, giữ datafile trong volume riêng, cấp secret an toàn và đợi SQL readiness trước khi chạy test. Container phù hợp với SQL/JDBC integration test và CI; VM phù hợp khi cần OS, native client hoặc isolation mạnh hơn. Dùng Oracle Database Free khi phù hợp điều kiện sản phẩm, kiểm tra license của mọi image/edition, không dùng dữ liệu production chưa mask và luôn phân biệt restart, recreate, reset volume với backup/restore. Một môi trường tốt phải tạo lại được, kiểm tra được và dọn sạch được sau mỗi lượt thử nghiệm.
