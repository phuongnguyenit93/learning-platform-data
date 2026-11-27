# RAC Services, Connection Distribution, and Service Placement Constraints

In Oracle Real Application Clusters (RAC), a single database can run across multiple instances accessing a shared set of database files. Applications need a stable way to connect and a mechanism for Oracle to distribute workloads across instances. Oracle RAC uses a **database service** as the logical entry point for applications and as the unit for managing workloads, placement, load balancing, high availability, and certain operational policies.

Services allow applications to connect by business purpose, such as OLTP, reporting, batch, or read-only workloads. Clusterware manages services and determines which instances a service can run on, which instances are preferred, when a service starts, and how a service reacts when an instance fails.

Three concepts must be distinguished:

- **Service** is a logical connection name representing a workload or application group. Applications specify the service name in the connect descriptor.
- **Service placement** is the set of constraints determining which instances or server pools a service runs on, how many instances serve it, and where standby/backup capacity resides.
- **Load balancing** is how connections or workloads are distributed across instances providing the service. Distributing connections at logon time and load balancing at runtime are two separate mechanisms.

## 1. Database Services in Oracle RAC

A database service is an attribute registered with the Oracle Net Listener and managed by Oracle Clusterware in a RAC environment. When an application connects using a service name, the listener locates an instance providing that service and directs the connection to an appropriate instance.

Example of a RAC database with three instances:

| Instance | Intended Role |
|---|---|
| RAC1 | Runs OLTP workload |
| RAC2 | Runs OLTP workload |
| RAC3 | Can take over OLTP if RAC1 or RAC2 fails |

A service named **oltp_rw.example.com** can be created for the transactional application. This service prefers RAC1 and RAC2, while RAC3 serves as an available instance. The application only configures the service name; if RAC1 fails, Clusterware can start or relocate the service on an available surviving instance according to the placement policy.

A service is an important abstraction because the application does not need to bind tightly to a specific instance. If an application connects directly to an instance SID or single node host, shifting workload during node failures becomes much harder to manage.

### Why Not Use One Shared Service for All Workloads?

Different workload types have different characteristics:

- OLTP requires low response times, many short sessions, and flexible connection distribution.
- Reporting or DSS involves long-running queries that typically consume more CPU, I/O, and memory.
- Batch processing may require steady execution windows and dedicated processing slots.
- Read-only workloads may be routed to a standby or dedicated instances depending on architecture.

Creating separate services per workload lets administrators tune placement, load balancing goals, resource plans, and failover policies, and monitor performance by application group. Service names can also serve as workload identifiers in resource management.

Do not create overly granular services for every individual application if they share the same operational requirements. Each additional service increases configuration, monitoring, and failover testing complexity.

## 2. Components Involved in Managing and Connecting Services

### Oracle Clusterware

Oracle Clusterware manages database and service resources in the cluster. Services are declared via SRVCTL and stored in Clusterware configuration. Clusterware monitors instance, node, and service states to perform starts, stops, relocations, or failovers according to policy.

In RAC, use **srvctl** to create and manage Clusterware-controlled services. Avoid using database-level manual service management commands in place of Clusterware placement configurations, as the two mechanisms can drift out of sync.

### Listener, SCAN, and Service Registration

The listener receives Oracle Net connections. In RAC, clients typically connect through **SCAN (Single Client Access Name)**. DNS resolves SCAN to SCAN VIPs; the SCAN listener accepts the connection and redirects the client to the local listener of an instance providing the service.

Instances register their services and endpoints with listeners via Oracle Net dynamic registration. In a standard RAC setup, Clusterware and related listener parameters handle this automatically.

Conceptual connection flow:

```text
        Application / Connection Pool
                    |
                    | SERVICE_NAME
                    v
             SCAN name (DNS)
                    |
           +--------+--------+
           |        |        |
           v        v        v
       SCAN L1  SCAN L2  SCAN L3
           \        |        /
            \       |       /
             \      v      /
        Listener selects instance
                    |
             +------+------+
             |             |
             v             v
           RAC1           RAC2
        OLTP service   OLTP service
             \             /
              \           /
                RAC3
            available instance
```

The diagram illustrates only the conceptual flow. The SCAN listener typically redirects the client to an appropriate local listener; actual connection handling also depends on service registration, instance state, listener settings, and client configuration.

### Clients and Connection Pools

Applications can connect directly or through a connection pool. Connection pools manage session counts, reuse connections, and can receive load balancing/failover notifications from Oracle when drivers and configurations support them.

Common components:

- Oracle JDBC Thin or OCI drivers.
- Oracle Universal Connection Pool (UCP).
- ODP.NET or compatible connection pools.
- ONS (Oracle Notification Service) to receive FAN events in supported architectures.

The ability to receive notifications and handle failover depends on the driver, version, connection pool, and configuration. Using a SCAN connect string alone does not automatically ensure an application can continue in-flight transactions when an instance fails.

## 3. Service Placement Constraints in RAC

Service placement determines where a service is allowed to run. Exact configuration depends on whether the database is **administrator-managed** or **policy-managed**.

### Administrator-Managed Databases

In the administrator-managed model, the DBA specifies exact instances for a service:

- **Preferred instances**: instances preferred to run the service under normal conditions.
- **Available instances**: fallback instances that can host the service if preferred instances become unavailable.

Example:

| Service | Preferred | Available |
|---|---|---|
| OLTP | RAC1, RAC2 | RAC3 |
| REPORTING | RAC3 | RAC1, RAC2 |
| BATCH | RAC2 | RAC1 |

While the OLTP service runs on RAC1 and RAC2, RAC3 does not necessarily run that service under normal conditions. If a preferred instance fails, Clusterware can start the service on an available instance based on configuration and remaining resources.

An available instance is a fallback location in the placement policy. It does not mean the application already has pre-established connections to that instance or that sessions running on the failed instance will automatically migrate seamlessly.

### Policy-Managed Databases

In the policy-managed model, services are associated with server pools rather than explicit instance lists. Clusterware manages server pool membership and allocates services by cardinality.

Two common cardinality modes:

- **UNIFORM**: the service can run on all eligible instances in the server pool.
- **SINGLETON**: the service runs on only one instance at a time within the server pool.

For example, a batch service can be configured as SINGLETON so only one instance executes that workload at a time. When the current instance fails, Clusterware can relocate the service to another instance in the pool if policies and resources allow.

Server pools also have min/max size, importance, and cluster administration constraints. Thus, service placement depends on both the service configuration and server pool state.

### Preferred and Available Are Not Load Balancing Mechanisms

Preferred/available defines the set of eligible instances and placement/failover behavior. Load balancing decides how connections or workloads are distributed among instances currently offering the service.

For example, a service has preferred RAC1 and RAC2. Both instances are running the service, yet if connection load balancing is misconfigured or the application does not use runtime load balancing, connections may still concentrate heavily on a single instance.

Therefore, configure separately:

1. Which instances are allowed to host the service.
2. How many instances run the service.
3. How listeners distribute new connections.
4. Whether the connection pool balances managed connections at runtime.

## 4. Creating and Managing Services with SRVCTL

Before creating a service, determine the database unique name, instance names, database management model, and workload policy. Inspect the database and service configurations with:

~~~bash
srvctl config database
srvctl config database -db RACDB
srvctl status database -db RACDB
srvctl config service -db RACDB
~~~

The names RACDB, RAC1, and RAC2 below are examples. Replace them with your actual db_unique_name and instance names.

### Creating a Service for Administrator-Managed RAC

Example creating an OLTP service, preferring RAC1 and RAC2, with RAC3 as an available fallback:

~~~bash
srvctl add service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC2 \
  -available RAC3 \
  -clbgoal SHORT \
  -rlbgoal SERVICE_TIME \
  -policy AUTOMATIC \
  -role PRIMARY
~~~

Meaning of key parameters:

- **-db**: database unique name managed by Clusterware.
- **-service**: name of the service to create.
- **-preferred**: list of preferred instances.
- **-available**: list of available fallback instances.
- **-clbgoal SHORT**: chooses a connection load balancing goal suited for short connections, typical of OLTP.
- **-rlbgoal SERVICE_TIME**: uses service time to evaluate load when runtime load balancing is supported.
- **-policy AUTOMATIC**: Clusterware manages starting the service automatically per policy.
- **-role PRIMARY**: runs the service only when the database has the PRIMARY role.

SRVCTL options and syntax may vary by Grid Infrastructure version and database type. Check the help output for your exact release before applying in production.

### Creating a Service for Policy-Managed RAC

For policy-managed databases, attach the service to a server pool and specify cardinality. Illustrative example:

~~~bash
srvctl add service \
  -db RACDB \
  -service batch_job \
  -serverpool batch_pool \
  -cardinality SINGLETON \
  -clbgoal LONG \
  -policy AUTOMATIC \
  -role PRIMARY
~~~

This service runs on only one instance in the server pool at a time. The server pool configuration must be capable of providing an eligible instance. Do not use preferred/available parameters from the administrator-managed model when configuring a server-pool-based service.

### Starting, Stopping, and Checking Status

~~~bash
srvctl start service -db RACDB -service oltp_rw
srvctl status service -db RACDB -service oltp_rw
srvctl config service -db RACDB -service oltp_rw
~~~

Stopping a service:

~~~bash
srvctl stop service -db RACDB -service oltp_rw
~~~

If the service policy is AUTOMATIC, Clusterware manages startup based on database state, placement, and policy. If the service uses MANUAL, an administrator or automation must start the service explicitly per procedure.

### Modifying Placement

You can change the instance list or service attributes using SRVCTL. Example:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC3 \
  -available RAC2
~~~

After modifying configuration, verify:

~~~bash
srvctl config service -db RACDB -service oltp_rw
srvctl status service -db RACDB -service oltp_rw
~~~

Plan placement changes during appropriate operational windows. Relocating or stopping/starting a service can disconnect active sessions unless the application has suitable failover/continuity mechanisms.

### Manually Relocating a Service

In administrator-managed RAC, you can move a service from an old instance to a new instance:

~~~bash
srvctl relocate service \
  -db RACDB \
  -service oltp_rw \
  -oldinst RAC1 \
  -newinst RAC3
~~~

This command illustrates moving a service currently running on RAC1 to RAC3. Parameter names may vary by release; consult SRVCTL help for your version. Before relocating, confirm RAC3 has sufficient CPU, memory, storage connectivity, and capacity to handle the workload.

## 5. Connect-Time Load Balancing

Connect-time load balancing distributes new connections across instances providing the service. The goal is to avoid piling all new clients onto one instance while other instances have spare capacity.

In RAC, SCAN and listeners let clients connect through a single common entry point. With multiple SCAN listeners, DNS can return multiple SCAN VIPs. Clients can try addresses according to the connect descriptor, while the listener routes the connection to an instance offering the service.

Example connect descriptor:

~~~text
(DESCRIPTION =
  (CONNECT_TIMEOUT = 5)
  (RETRY_COUNT = 3)
  (RETRY_DELAY = 2)
  (ADDRESS =
    (PROTOCOL = TCP)
    (HOST = rac-scan.example.com)
    (PORT = 1521)
  )
  (CONNECT_DATA =
    (SERVICE_NAME = oltp_rw.example.com)
  )
)
~~~

Easy Connect can also be used:

~~~text
//rac-scan.example.com:1521/oltp_rw.example.com
~~~

Clients should use **SERVICE_NAME**. In RAC, avoid using a single instance's SID as the general connection target for applications requiring HA and connection distribution.

### Load Balancing in ADDRESS_LIST

A connect descriptor can contain multiple listener addresses. The LOAD_BALANCE attribute controls how Oracle Net selects among addresses inside ADDRESS_LIST. This is address selection at the Oracle Net layer; it does not replace service-level connection load balancing or runtime load balancing.

General example with multiple listener addresses:

~~~text
(DESCRIPTION =
  (LOAD_BALANCE = ON)
  (ADDRESS_LIST =
    (ADDRESS = (PROTOCOL = TCP) (HOST = listener-a.example.com) (PORT = 1521))
    (ADDRESS = (PROTOCOL = TCP) (HOST = listener-b.example.com) (PORT = 1521))
  )
  (CONNECT_DATA =
    (SERVICE_NAME = oltp_rw.example.com)
  )
)
~~~

LOAD_BALANCE in ADDRESS_LIST applies when a descriptor has multiple ADDRESS entries; it governs how Oracle Net attempts listener addresses in the list. The example above demonstrates the general Oracle Net mechanism, not a requirement to create two SCAN names. With RAC, clients typically only need one SCAN name; DNS returns the SCAN VIPs and the SCAN listener routes to the appropriate local listener. Avoid manually listing individual node VIPs as a replacement for SCAN.

### Connection Load Balancing Goal

A service has a CLB goal attribute to guide how listeners distribute connections:

- **SHORT**: suited for workloads with short-lived connections, high connection rates, and relatively brief request processing times. The goal is to distribute connections based on service/instance load to reduce response times.
- **LONG**: suited for long-lived connections, such as connection pools holding sessions open for extended periods. The listener evaluates load appropriately for persistent connections rather than optimizing solely for short connection bursts.

The CLB goal is not a guarantee that every instance will have the exact same session count. CPU load, processing times, session counts, listener setup, and service policies all influence distribution.

## 6. Runtime Load Balancing and FAN

Connect-time load balancing only decides where to place a new connection when a client logs on. Once a connection pool has opened many sessions and holds them long-term, load across instances can shift. One instance may become busier while existing pooled connections remain attached to it.

**Runtime load balancing (RLB)** uses service load advisories published by Oracle while the database is running. Compatible connection pools can use this information to pick the best instance when borrowing a connection for a new request.

### RLB Goal

A service can use one of the common goals:

| RLB Goal | Meaning | Suitable Workload |
|---|---|---|
| SERVICE_TIME | Balances by service/response time | OLTP, latency-sensitive requests |
| THROUGHPUT | Balances by throughput | Batch or high-volume processing workloads |

Choose the goal based on actual application objectives. A latency-sensitive workload may select SERVICE_TIME; a workload prioritizing aggregate throughput may select THROUGHPUT. RLB only takes effect when the client pool/driver supports it and is configured to receive and act on runtime load balancing advisories.

### FAN Events

Fast Application Notification (FAN) delivers notifications about cluster events such as instance up/down, service up/down, and state changes. Applications or connection pools integrated with FAN can rapidly evict connections to failed instances, recognize when a service starts on another instance, and open new connections to healthy targets.

Service notification can be enabled in service configuration:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -notification TRUE
~~~

FAN notifications require ONS infrastructure and compatible clients. Simply enabling notification on the service does not automatically make an arbitrary application process events. Verify ONS configuration, driver version, pool settings, and connection invalidation handling.

### Connection Pools and Runtime Balancing

In Java environments, Oracle UCP can integrate with FAN and runtime load balancing. The connection pool receives service/instance status advisories and uses them when selecting a connection for a request. With JDBC Thin, use a compatible driver version and pool configuration supporting the required features.

If an application uses a pool without FAN/RLB integration, already-established connections may remain concentrated on one instance even after load shifts. In such cases, review pooling strategy, connection lifetime/max-age, pool limits, and reconnection behavior.

## 7. Service Placement by Database Role

In a Data Guard architecture, a database can switch roles between PRIMARY and PHYSICAL STANDBY. Some services should only run when the database is PRIMARY; others are meant for reporting on a standby.

A service can be bound to a database role:

~~~bash
srvctl add service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC2 \
  -available RAC3 \
  -role PRIMARY \
  -policy AUTOMATIC
~~~

Example service dedicated to reporting queries on a physical standby:

~~~bash
srvctl add service \
  -db RACSTBY \
  -service reporting_ro \
  -preferred STBY1,STBY2 \
  -role PHYSICAL_STANDBY \
  -policy AUTOMATIC
~~~

Database, instance, and role names are illustrative. In Data Guard environments, coordinate service roles with Data Guard Broker, Clusterware, and switchover/failover procedures. After a database changes role, eligible services can automatically start or stop per role configuration. This allows applications to continue using the same service name after a role transition if the architecture and connect strings are designed accordingly.

A service role does not by itself make a service read-write or read-only. Ensure open mode, database role, session privileges, and application configuration align.

## 8. Services and High Availability on Instance Failure

When an instance fails, Clusterware detects the fault and executes resource recovery policies. If the service has an available fallback instance or a server pool replacement instance, Clusterware can start the service there.

Distinguish three layers:

1. **Service failover/relocation**: the service starts on another instance to accept new connections.
2. **Client reconnect**: the application reconnects via SCAN/service name and the listener routes it to an active instance providing the service.
3. **Session or transaction continuity**: the application resumes sessions or transactions via mechanisms such as TAF, Application Continuity, or Transaction Guard when conditions, drivers, and configurations support them.

Having the service appear on another instance does not mean old sessions migrate intact. Sessions on the failed instance are typically lost. Clients must reconnect; to continue in-flight requests or replay transactions, configure and test an appropriate continuity mechanism.

### TAF

Transparent Application Failover (TAF) assists clients in reconnecting and, in some cases, recovering sessions or select cursors within TAF's configuration and limits. TAF can use failover type SESSION or SELECT depending on the driver and service.

Illustrative service configuration example:

~~~bash
srvctl modify service \
  -db RACDB \
  -service reporting_ro \
  -failovertype SELECT \
  -failovermethod BASIC \
  -failoverretry 30 \
  -failoverdelay 5
~~~

Failover options and support depend on Oracle release, client type, and workload. SELECT failover can re-execute a fetching query under certain conditions; it does not mean every in-flight transaction is recovered.

### Application Continuity and Transaction Guard

Application Continuity (AC) can replay eligible requests/transactions after a connection failure, reducing disruption impact on the application. Transaction Guard helps determine a transaction's commit outcome so the application avoids blindly re-submitting a transaction whose commit status was ambiguous.

Services supporting AC may require attributes such as failover type TRANSACTION, commit outcome, replay initialization time, and session state consistency. The example below merely illustrates the parameter group; verify release and driver compatibility before deployment:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -failovertype TRANSACTION \
  -commit_outcome TRUE \
  -replay_init_time 600 \
  -session_state_consistency DYNAMIC
~~~

Do not enable these attributes without verifying that the application satisfies replay prerequisites. Applications with external side effects, non-idempotent operations, or unmanaged session state may need special handling. Test real failure scenarios before relying on AC for transaction continuity.

## 9. Services and Workload Resource Management

Services can also serve as the basis for classifying workloads in Oracle Database Resource Manager. DBAs can map sessions to consumer groups by service name, module, action, or other attributes.

For example, OLTP and REPORTING services can be assigned to separate consumer groups to control CPU priority, parallelism, or resource limits. This prevents heavy reporting workloads from starving resources needed by transactional applications.

A service does not automatically create a resource plan. You must configure an appropriate Resource Manager plan and mapping rules. Inspect services and sessions using views such as:

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal
FROM   gv$services
ORDER BY name, inst_id;
~~~

For currently connected sessions:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       service_name,
       username,
       machine,
       program
FROM   gv$session
WHERE  type = 'USER'
ORDER BY service_name, inst_id;
~~~

GV$ views allow observing across multiple RAC instances. Access depends on account privileges and dictionary permissions. Displayed columns can vary by release; verify against the data dictionary on your target version.

## 10. Verifying Service Placement and Connections

### Viewing Service Configuration

~~~bash
srvctl config service -db RACDB
srvctl config service -db RACDB -service oltp_rw
~~~

Details to verify:

- Service name and network name.
- Preferred/available instances or server pool/cardinality.
- Management policy: AUTOMATIC or MANUAL.
- Database roles permitted to run the service.
- CLB goal and RLB goal.
- Notification and failover/continuity attributes.
- Any resource plan or workload attributes if configured.

### Viewing Cluster Service Status

~~~bash
srvctl status service -db RACDB
srvctl status service -db RACDB -service oltp_rw
~~~

The output shows which instances are currently running the service. If a service is not running where expected, check instance status, placement policy, server pools, resource dependencies, and Clusterware logs.

### Checking Listeners

From the database host or a machine with Oracle Net tools, check listener service registration using:

~~~bash
lsnrctl services LISTENER
~~~

Listener names may vary by environment. For SCAN listeners, use the corresponding listener name or Grid Infrastructure administration tools. Confirm the service is registered, handlers are ready, and the listener recognizes the correct network service name.

### Checking Services Inside the Database

~~~sql
SELECT inst_id,
       name,
       network_name,
       creation_date
FROM   gv$services
ORDER BY name, inst_id;
~~~

To see which services sessions are connected through:

~~~sql
SELECT inst_id,
       service_name,
       COUNT(*) AS session_count
FROM   gv$session
WHERE  type = 'USER'
GROUP BY inst_id, service_name
ORDER BY service_name, inst_id;
~~~

Session count is only one indicator. An instance with fewer sessions may still be busier if those sessions execute long-running or resource-intensive queries. Combine session count with CPU, response time, active sessions, wait events, and runtime load balancing metrics.

## 11. Modifying Services and Testing Failover

Before modifying services in production, assess the impact on active sessions, pools, and applications. Certain changes may require restarting or relocating the service to take effect.

A testing procedure should include:

1. Record current configuration via SRVCTL and service status.
2. Confirm applications connect using SCAN and SERVICE_NAME.
3. Record session counts, CPU load, response times, and connection distribution per instance.
4. Test stopping or relocating the service in a test environment.
5. Observe listener redirection, FAN events, and connection pool behavior.
6. Test an instance failure scenario, verifying service startup on the available instance and client reconnection.
7. If using TAF/AC, test in-flight queries, active transactions, and commit outcomes.
8. Restore configuration after testing and confirm the service runs in its intended placement.

Avoid stopping a production instance solely to prove failover without a maintenance window and application coordination plan. Validate first via service relocation or an appropriate staging environment.

## 12. Common Issues

### Application Connects to a Fixed Instance

The usual cause is a connect string specifying a node host/VIP or SID instead of SCAN and service name. Check datasource URLs, `tnsnames.ora`, and pool configurations. Use the SCAN hostname with SERVICE_NAME so clients can be routed to any instance hosting the service.

### Service Not Running on Expected Instance

Check preferred/available instances, server pools, cardinality, role, management policy, and instance status. If an instance does not satisfy placement constraints or prerequisites, Clusterware will not start the service there.

### Service Running, Yet Connections Are Unbalanced

Check CLB goal, listener registration, handler states, and how clients open connections. For pools holding long-lived sessions, connect-time load balancing affects only new connections. Runtime balancing requires a driver/pool supporting RLB and FAN.

### Service Relocates, Yet Application Still Errors

Service relocation only establishes a target for new connections. Applications may still hold stale connections or experience interrupted transactions. Check FAN integration, timeouts, retries, TAF or Application Continuity, and application error-handling logic.

### FAN Events Not Reaching the Connection Pool

Verify service notification settings, ONS configuration, network connectivity between clients and ONS, driver version, and pool configuration. FAN only works when the application stack has a component receiving and acting on events.

### Preferred Instance Fails, Yet Service Does Not Relocate

Check the available instance list, AUTOMATIC/MANUAL policy, database role, server pool, and Clusterware resource states. Inspect CRS/Clusterware logs and SRVCTL output to determine why the service did not start on the fallback location.

### Uneven Connection Distribution Even With DOP or CLB Configured

CLB goal does not guarantee strictly equal session counts. Connections have varying lifetimes, connection pools hold sessions open, and instances may differ in capacity or workload. Evaluate response time, throughput, active sessions, and actual load rather than merely counting sessions.

## 13. Service Design Process for RAC

1. **Group workloads.** Separate OLTP, reporting, batch, and read-only workloads with distinct latency, throughput, and runtime requirements.
2. **Name services clearly.** Use names reflecting function and environment, such as `oltp_rw` or `reporting_ro`.
3. **Identify database model.** Check whether administrator-managed or policy-managed is used to select preferred/available or server pool/cardinality.
4. **Set placement constraints.** Define preferred instances, available instances, instance count, and permitted database roles.
5. **Choose CLB/RLB goals.** Base on short/long connection profiles and response-time/throughput objectives.
6. **Configure connectivity.** Use SCAN and SERVICE_NAME; set sensible timeouts/retries in the connect descriptor or driver.
7. **Configure HA.** Choose notifications, FAN, TAF, or Application Continuity aligned with client capabilities and transaction requirements.
8. **Integrate resource management.** Map services to consumer groups/resource plans when workload isolation is required.
9. **Verify at runtime.** Observe service placement, listener registration, session distribution, and per-instance response times.
10. **Rehearse failover.** Test instance failures, service relocation, client reconnection, and transaction continuity per application scenarios.

## 14. Key Operational Principles

- Use service names as stable connection endpoints for RAC applications; prefer SCAN over individual node hosts/VIPs.
- Design services per workload so appropriate placement, load balancing, and resource plans can be applied.
- Use preferred/available for administrator-managed databases; use server pools/cardinality for policy-managed databases.
- Distinguish placement from load balancing. A service may run on the right instances while connections remain unevenly distributed.
- Configure CLB and RLB goals based on actual objectives; verify whether client pools support runtime load balancing.
- Enable FAN notifications when applications and connection pools can receive and handle events.
- Do not assume service relocation automatically recovers sessions or transactions. Appropriate client reconnect, TAF, or Application Continuity mechanisms are required.
- With Data Guard, bind services to database roles so workloads run only on the appropriate role.
- Verify SRVCTL, listener registration, GV$SERVICES, and GV$SESSION after making changes.
- Test relocation/failover in suitable environments and monitor the impact on applications.

Services are the core unit of connectivity and workload management in Oracle RAC. When placement constraints, SCAN/listeners, connect-time load balancing, runtime load balancing, and client failover mechanisms are properly combined, applications leverage the cluster more flexibly, distribute load effectively, and recover connections cleanly when instances fail.
