# Transfer Appliance and Large-Scale Data Migration

## 1. Lesson Objectives and Context

During **migration to Google Cloud**, enterprises do not only move virtual machines or applications—they must also transfer datasets spanning tens to hundreds of terabytes from existing data centers to the cloud. When network bandwidth is constrained, uploading over the Internet alone can take weeks or months, delaying system cutover schedules.

**Google Cloud Transfer Appliance** is a high-capacity storage appliance provided by Google to capture data at the customer's site and transfer it into **Cloud Storage**. In **offline mode**, the customer copies data onto the appliance, seals it, and ships it back to Google; Google ingests the data into the target bucket. Certain devices support **online mode**, allowing the appliance to stream data over the network to Cloud Storage while in use.

This lesson fits into the **CLOUD_PROVIDERS_GCP** learning track: from project organization, IAM, VPC, storage, and databases to deployment, reliability, and cost tracking. Here, Transfer Appliance serves as the **initial bulk ingestion vehicle into Cloud Storage** so downstream services such as Dataflow, BigQuery, GKE, or Cloud Run can consume the data within the target architecture.

After this lesson, you will be able to:

- Explain how Transfer Appliance works and compare offline mode vs. online mode.
- Estimate network transfer duration, appliance copy duration, and capacity requirements.
- Choose between Transfer Appliance, Storage Transfer Service, and CLI tools based on real constraints.
- Plan security, appliance receiving, copying, sealing, shipping, and data verification.
- Recognize limitations around files, regional availability, data consistency, and application cutover timing.

## 2. Why Does Large Data Become a Migration Bottleneck?

Suppose an enterprise has **180 TB** of images, videos, logs, and archive files on an internal NAS. A dedicated transfer link has a nominal **200 Mbps** capacity and roughly **75%** average usable throughput efficiency.

Minimum transfer time under a simple model:

~~~text
Time (days)
  = Size (TB) × 10^12 (bytes/TB) × 8 (bits/byte)
    / [Bandwidth (Mbps) × 10^6 × Efficiency × 86,400 (seconds/day)]

With 180 TB, 200 Mbps, and 0.75 efficiency:
  = 180 × 10^12 × 8 / (200 × 10^6 × 0.75 × 86,400)
  ≈ 111 days.
~~~

This is strictly a **pure transmission estimate**. Actual duration is also affected by source read speeds, file counts, authentication overhead, latency, packet loss, retries on failures, peak-hour contention, and ongoing data churn during transfer. If that link also serves live applications, you cannot assume all 200 Mbps are available for bulk upload.

With an **offline Transfer Appliance**, the same 180 TB is copied over the local LAN to the appliance. At a **measured effective write rate** of 500 MB/s, theoretical copy time alone is roughly:

~~~text
180 × 10^12 bytes / (500 × 10^6 bytes/sec) / 86,400
≈ 4.17 days.
~~~

To that you must still add appliance provisioning, setup, inspection, shipping both ways, Google ingestion, and validation. Never quote 4.17 days as the end-to-end project timeline.

**Core idea:** copy quickly over LAN to the appliance, then move massive capacity to Google via physical shipping; end-to-end effectiveness depends on the entire chain, not capacity or bandwidth alone.

## 3. How Does Transfer Appliance Work?

~~~mermaid
flowchart LR
    A["NAS / file server / on-premises storage"] -->|"NFS, SMB, or SCP/SFTP"| B["Transfer Appliance"]
    B -->|"Offline: seal and ship appliance"| C["Google intake facility"]
    C -->|"Secure data ingestion"| D[("Cloud Storage bucket")]
    B -.->|"Online: transfer over network if configured"| D
    D --> E["Verify, process, and consume data on Google Cloud"]
~~~

In **offline mode**, the general flow is:

1. Survey the dataset, verify the physical installation site, and request an appliance model.
2. Create or identify the target project and Cloud Storage bucket, and prepare access permissions.
3. Receive the appliance, inspect physical tamper seals, and run **attestation** before connecting it to the internal network.
4. Connect networking, configure a transfer protocol, and copy data onto the appliance.
5. Reconcile file counts, sizes, and copy errors; run the finalize command to close the write session.
6. Seal and hand off the appliance to the carrier per Google instructions.
7. Google verifies the appliance, ingests data into the bucket, writes result logs, and erases data from the appliance.
8. Customer verifies data in Cloud Storage before deciding to retire source storage.

**Key distinction:** Transfer Appliance does not automatically turn files into a database, migrate VMs into Compute Engine, maintain continuous application-level replication, or preserve every filesystem semantic (ACLs, symbolic links, hard links, or POSIX attributes) inside object storage.

### Appliance Models and Key Capabilities

Per Transfer Appliance 4.0 specifications published by Google as of November 2026:

| Appliance Line | Max Usable Encrypted Data Capacity | Notes |
| --- | ---: | --- |
| TA40 / TA40F | 40 TB | Rack-mountable or standalone form factor |
| TA300 / TA300F | 300 TB | Rack-mountable or standalone form factor |
| Multi-appliance orders | Depends on Google-approved appliance count | Datasets can be split for parallel copying |

Devices use SSD storage; data ports include 10 Gbps RJ45 and 100 Gbps QSFP28 **on corresponding rack models**. Port specs indicate physical link capability, **not guaranteed sustained write speed**. Account for source read speeds, switches, file layout, protocol overhead, thread concurrency, and processing speed.

Before ordering, verify **currently offered models, usable capacity, physical dimensions, 100–240 V / 50–60 Hz power, cooling requirements, floor/rack space, and shipping/receiving constraints**. Listed capacity is the maximum ceiling; leave headroom based on survey results.

### Offline Mode vs. Online Mode

| Criterion | Offline | Online |
| --- | --- | --- |
| Link to Cloud Storage | Does not use the Internet to upload all data from the device | Requires network connectivity to Google Cloud |
| When data arrives in Cloud Storage | After Google receives and ingests the appliance | Device streams data incrementally to Cloud Storage |
| Temporary data staging | Device storage until ingestion completes and device returns | Device storage acts as a buffer; data is cleared from buffer after successful upload |
| Best suited for | Massive datasets, constrained or unstable WAN links | Incremental ingestion leveraging existing network bandwidth |
| Operational notes | Involves sealing, shipping, and post-receipt ingestion | Requires service account, IAM permissions, and live connectivity |

When **ordering an online-capable model**, you can switch between online and offline modes per instructions. Appliances **ordered strictly as offline-only** cannot enable online mode after delivery. Mode selection must be decided at order time.

## 4. When Should You Choose Transfer Appliance?

No single TB threshold guarantees Transfer Appliance beats every alternative. Google suggests it is a good fit when **network upload would take more than a week** and the customer's site is in a supported location.

| Scenario | Tool to Evaluate First | Rationale |
| --- | --- | --- |
| Small dataset from a local host | Google Cloud CLI, e.g., `gcloud storage` | Simple with minimal setup |
| NAS/on-premises data, stable WAN, periodic sync needed | Storage Transfer Service with agents | Streams over the network and syncs changes |
| Data in Amazon S3 or Azure Blob | Storage Transfer Service | Cloud-to-cloud object transfer |
| Tens/hundreds of TB at a bandwidth-constrained site | Transfer Appliance offline | Eliminates WAN bottleneck for bulk initial ingestion |
| Large data streaming to Cloud Storage while copying locally | Transfer Appliance online | Combines LAN copy staging with online upload |
| Transactional live database | Database-specific migration service/model | Requires transactional consistency, CDC, and controlled cutover |

**The evaluation must cover all four axes:**

- **Size and file distribution:** TB, file count, typical sizes, small-file ratio, directory depth, and daily growth.
- **Transfer capacity:** actual outbound bandwidth, peak-hour caps, source read throughput, and LAN performance.
- **Cutover deadline:** date data must land in Cloud Storage and date applications must cut over.
- **Operational constraints:** whether the site can receive hardware, physical security controls, data regulations, and budget.

### Total Time Comparison Formula

~~~text
T_online  = Network transfer time + verification + ongoing delta sync
T_offline = Order/delivery time
          + copy time from source -> appliance
          + reconciliation and finalize time
          + return shipping time
          + Google ingestion time into Cloud Storage
          + verification and cutover time
~~~

Even if Transfer Appliance wins on initial bulk load, if **significant new or modified data** accumulates while the device is in transit, the team still needs a **delta plan**: freeze the source at a checkpoint, sync changes via an online tool, or plan an extra copy pass. Never assume an appliance in transit magically syncs ongoing source changes.

## 5. Surveying Data and Planning Capacity

Before ordering an appliance, catalog source datasets and assign an owner to each:

| Attribute to Collect | Verification Question |
| --- | --- |
| Actual and projected size | How many TB exist today? How many TB are added daily? |
| File count and distribution | Millions of KB-sized files, or mostly multi-GB files? |
| Format | Regular files, archives, snapshots, DB exports, or symlinks? |
| Consistency requirements | Do applications modify files while copying? |
| Classification and compliance | Sensitive data, residency rules, or chain-of-custody controls? |
| Accessibility | Does the copy account have read permissions across all paths? |
| Destination | Target project, bucket, location, object prefix, storage class, and lifecycle? |
| Acceptance criteria | Which manifest serves as the source of truth for post-transfer reconciliation? |

Basic survey examples on a **Linux source host using GNU coreutils**:

~~~bash
# Source size in bytes; output is for survey purposes only.
du -sb /data/archive

# Count regular files (excluding directories).
find /data/archive -type f -printf '.' | wc -c

# Separately inspect symbolic links that must be handled before object storage ingestion.
find /data/archive -type l -print
~~~

If the dataset changes during copying, prepare a **consistent snapshot** or equivalent mechanism before starting. Never treat a single capacity scan as proof that data is static.

### Data Limits to Watch

Per Google Cloud Transfer Appliance 4.0 workflow guidelines:

- Files must be **regular files** or Unix-style hidden files. Handle symlinks, special files, and filesystem-specific objects separately.
- Individual files must be **smaller than 5 TB** per Transfer Appliance constraints, while also meeting Cloud Storage object limits.
- Filenames must comply with **Cloud Storage object naming** rules.
- Maximum object path length is **1,024 bytes**, including any optional object prefix.
- Empty directories do not automatically become objects in a bucket. Cloud Storage uses an **object** model, not a full POSIX filesystem.
- Transfer Appliance **does not guarantee catching every filename/size violation during copy**; invalid data may fail Google ingestion.

With huge file counts, per-file metadata and creation overhead can dominate total TB volume. Packaging static files into archives may make sense when aligned with downstream usage, factoring in extraction cost and future object accessibility. Never compress or bundle blindly just to chase a benchmark number.

### Choosing Appliance Count

For 180 TB of regular data, choose **one TA300** rather than multiple TA40s if facility specs and copy throughput allow. For 420 TB, you may need **multiple appliances**, partitioning datasets with explicit manifests to prevent duplicate or skipped paths. Google confirms model, quantity, and delivery logistics prior to deployment.

Leave buffer for data growth, estimation variance, and operational overhead. Never order near 100% of rated capacity assuming everything will fit tightly.

## 6. Preparing Google Cloud and Security Policies

### Project, Bucket, and IAM

1. Choose the **Google Cloud project** holding the order configuration and identify the **target Cloud Storage bucket**. Per standard flow, register Transfer Appliance in the same project as the destination bucket.
2. Verify **bucket location**, data residency requirements, retention policies, storage class, versioning, and ongoing storage costs. Successful ingestion does not automatically mean the right long-term storage setup was chosen.
3. Prepare administrative permissions to complete the setup checklist; grant the session/appliance service account bucket access per official guidance and **least privilege**.
4. If using online mode, enable required permissions and APIs for **Transfer Appliance, Pub/Sub, and Storage Transfer Service**, along with appropriate service accounts. Protect service account keys per policy; never put keys in repositories, terminal logs, or public docs.
5. If using customer-managed encryption keys, coordinate with security to prepare **Cloud KMS** and key lifecycle policies. Never delete or disable a key required for an active transfer session.

Ordering permissions, object write permissions, post-transfer read permissions, and KMS management are distinct responsibilities—assign and verify them upfront.

### Protecting Data and the Appliance

Transfer Appliance verifies device integrity via **hardware attestation/TPM**, encrypts data at rest on the appliance using **AES-256**, and uses a **data encryption key (DEK)** wrapped by a **key encryption key (KEK)**. For supported sessions, the KEK can be Google-managed or customer-managed via Cloud KMS. Google verifies the appliance on intake before ingesting data, then executes data erasure per published procedures.

**Boundary to remember:** Google explicitly notes it does not enforce a separate encryption layer between your internal data source and the Transfer Appliance. The operations team owns securing that local segment. When using NFS, SMB, or other protocols, apply network segmentation, host allowlists, port restrictions, physical access controls, and suitable transfer methods. If policy mandates encryption across the LAN hop, evaluate supported encrypted protocols with security.

Record appliance custody handoffs, operators, seal numbers, session IDs, attestation results, and session closure status. Afterward, review procedures for requesting a **certificate of data erasure** if enterprise compliance requires one.

### Country Availability

Transfer Appliance **is not automatically deliverable in every country**. Overview docs list markets such as the United States, EU member states, the United Kingdom, Singapore, Japan, Canada, and India, though availability and models vary by region. If executing a project in **Vietnam**, check country/address availability in the Google Cloud order form and confirm with support before locking the architecture; never assume having a Google Cloud project guarantees hardware delivery.

## 7. End-to-End Offline Deployment Workflow

### Step 1 — Design the Data Transfer Plan

- Select datasets, buckets, object prefixes, and the manifest cutoff point.
- Define how long the source copy stays intact post-cutover.
- Schedule ordering, appliance arrival, copying, reconciliation, return shipping, and final validation.
- Assign owners for infrastructure, IAM/KMS, copying, and acceptance.
- Lock how changes occurring during shipping and ingestion will be handled.

### Step 2 — Order the Appliance and Complete the Setup Checklist

Open Transfer Appliance in the Google Cloud Console, choose the model and mode, and configure the destination bucket, permissions/keys, and shipping address per current guidance. Never treat shipping estimates as an SLA; lead times vary by country, shipping season, hardware stock, and order status.

### Step 3 — Receive, Verify, and Configure the Appliance

Before connecting the appliance to the internal network:

1. Inspect packaging, tamper seals, and shipment contents.
2. Run the **Transfer Appliance Attestation** app per instructions to obtain a passcode.
3. Verify the passcode through Google Cloud's workflow to retrieve access credentials after successful attestation.
4. Configure data ports, IP, DNS, power, and connect to a controlled network segment.
5. Enable **one file-sharing protocol** matching your source OS.

Note: current documentation specifies **each appliance configures one file-sharing protocol at a time**. Changing protocols later may require resetting the appliance, causing **loss of copied data**. If two protocols are needed, confirm the approach with Google upfront.

### Step 4 — Copy Data to the Appliance

**Illustrative Linux example using NFSv4**, assuming the appliance is configured and sample IP `192.0.2.10` is reachable from the source host:

~~~bash
# On the Linux source host; run only after NFS is configured on the appliance.
sudo mkdir -p /mnt/ta
sudo mount -t nfs -o vers=4 192.0.2.10:/mnt/ta_data /mnt/ta

# Example copying regular files under archive.
# Evaluate behavior for special files, symlinks, and permissions before running.
rsync -r --partial --info=progress2 /data/archive/ /mnt/ta/archive/
~~~

This illustrates command structure; substitute your actual appliance IP, paths, and authentication. The target mount path on the appliance is `/mnt/ta_data`. Linux/macOS typically uses NFS; Windows typically uses SMB or SFTP/SCP. Avoid changing protocols after writing data. Run copy commands inside `tmux`/`screen` or a managed session to survive SSH disconnects.

Do not copy from a continuously mutating source when strict consistency is required. After initial copy, verify copied data against the locked snapshot/manifest.

### Step 5 — Monitor Progress and Errors

In the Transfer Appliance CLI environment, for example:

~~~bash
ta status
ta status --verbose
~~~

Monitor used capacity, remaining capacity, drive/network errors, transferred bytes, and copy rate. Google also supports tracking Transfer Appliance metrics via Cloud Monitoring when properly configured.

For multiple sources, partition datasets into labeled batches (e.g., photo archive 2018–2020, 2021–2023, 2024–2026). Log source, file count, byte size, snapshot timestamp, and errors per batch. Resolve copy failures or invalid filenames before closing the session.

### Step 6 — Verify and Finalize

Before running the session-ending command, verify:

- All batches in the manifest copied completely; open errors are resolved or formally accepted.
- Full or sampled content hashes match per risk requirements.
- No processes are still writing to the appliance.
- Audit records are saved and the delta plan is ready.

The `ta finalize` command closes the copy session to prepare the appliance for return. This action **irreversibly prevents further writes**: the appliance clears keys and configuration per finalization procedures, so run it only after full verification. In an active session, follow official instructions and save the returned **passcode** to obtain return shipping labels.

~~~bash
# Run on the appliance only after all data has been verified.
ta finalize
~~~

### Step 7 — Ship the Appliance Back

Pack, seal, apply the session-specific return label, and log chain of custody. Google receives and verifies the appliance, then ingests data into Cloud Storage.

### Step 8 — Verify Data Ingested into Cloud Storage

Consider the transfer finished only when verified in the **destination bucket**, not merely when the carrier marks the package delivered. Per Google guidance, inspect:

- Completion notice from the Transfer Appliance team.
- Actual objects present in the target bucket and prefix.
- Success/failure CSV logs under paths similar to:

~~~text
gs://DESTINATION_BUCKET/transferappliance/logs/SESSION_ID/TIMESTAMP/transferred/
gs://DESTINATION_BUCKET/transferappliance/logs/SESSION_ID/TIMESTAMP/failedtotransfer/
~~~

Reconcile file paths, counts, sizes, and errors. Sample critical files to download, verify checksums, test decompression, or run application reads. If any objects failed ingestion, build a retry list—never delete originals yet.

### Step 9 — Complete Cutover and Clean Up Source Data

After successful reconciliation, decide when to switch applications to Cloud Storage paths and transfer any incremental deltas. Test access permissions, performance, processing workflows, and retries. End on-premises source retention only after data owners approve based on acceptance results, retention policy, and recovery plans.

## 8. Data Acceptance Criteria

Use this table as input for the acceptance sign-off record:

| Check | Verification Method | Suggested Criterion |
| --- | --- | --- |
| Completeness | Compare source manifest against destination object list | Zero unexplained missing files |
| Ingestion errors | Inspect failed-to-transfer CSV logs | Zero unresolved errors |
| Integrity | Compare checksums across full set or risk-based sample | Matches expected content |
| Structure | Inspect object names, prefixes, and partitioning | Conforms to target data conventions |
| Usability | App test reads; Dataflow/BigQuery sample runs | Accurate output, zero permission errors |
| Security | Verify IAM, location, KMS, and retention policies | Matches approved design |
| Incremental churn | Compare snapshot baseline with current source | Delta handling plan executed |
| Evidence | Archive manifests, logs, and custody records | Full transfer session traceability |

**On checksums:** Cloud Storage uses its own object checksum/metadata formats; do not assume every object exposes an MD5 directly comparable to local file hashes. Agree upfront on hash algorithms, manifest generation, path mapping, and sample re-read verification. For high-value data, compute strong source hashes and re-verify when reading back objects.

## 9. Common Risks and Mitigations

| Risk | Symptom | Mitigation |
| --- | --- | --- |
| Underestimated capacity | Appliance fills up before copy completes | Measure in bytes, add growth and buffer; split across appliances if needed |
| Huge count of tiny files | Moderate TB yet very slow throughput | Benchmark representative sample; optimize copy strategy and concurrency |
| Invalid names/paths or files | Objects missing after Google ingestion | Scan against Cloud Storage and Transfer Appliance limits before copying |
| Source mutates mid-copy | Hashes or file counts diverge from manifest | Snapshot, freeze baseline, and sync deltas separately |
| Wrong bucket or KMS permissions | Ingestion or decryption blocked | Verify IAM/KMS checklist and key lifecycle ahead of time |
| Insecure internal network | Data exposure risk between source and appliance | Segment network, restrict hosts, use approved transfer protocols |
| Interrupted copy session | Copy aborts mid-transfer | Use resumable tooling, keep logs, and verify after errors |
| Premature finalization | Cannot write remaining data to appliance | Enforce reconciliation and checkpoint before running `ta finalize` |
| Appliance unavailable at site | Order unsupported in target country | Confirm geography and delivery logistics before approving architecture |
| Confusing file copy with app migration | Files land in bucket yet application fails | Plan separately for databases, APIs, IAM, and app endpoints |

## 10. Real-World Costs and Timelines

When evaluating total migration cost (TCO), account for at least:

1. **Service/appliance and logistics fees:** appliance model, quantity, usage duration, and shipping terms per active quote or pricing schedule.
2. **Internal costs:** engineering time, operational labor, network gear, snapshots, extra load on NAS, and security controls.
3. **Post-ingestion Google Cloud costs:** Cloud Storage capacity, storage classes, API operations, retrieval, data processing, and replication.
4. **Online delta costs:** network links, designed traffic, Internet caps, and carrier billing terms if applicable.
5. **Risk costs:** delayed cutover, rework from data defects, and prolonged parallel-run of two environments.

Never pick an option solely on appliance rental price or Cloud Storage per-GB cost. Compare **total cost + total elapsed time + risk tolerance**.

Illustrative **sample schedule** for 180 TB:

| Phase | Activities | Deliverables |
| --- | --- | --- |
| Prep week | Survey, pick bucket region, confirm availability, set IAM | Inventory, manifest plan, delta transfer plan |
| Appliance receipt | Attestation, network setup, small-sample test | Operational appliance, measured throughput |
| Copy | Copy frozen source data and verify | Required data written, zero unresolved errors |
| Return | Finalize, seal, ship back | Passcode, chain-of-custody record |
| Ingestion & acceptance | Google loads bucket; team reconciles | Acceptance sign-off, residual error list |
| Cutover | Transfer deltas and test applications | Applications consuming data on GCP |

These rows show **work sequence**, not guaranteed day counts. Google documentation cites roughly three weeks end-to-end as a general guideline; exact timelines must be confirmed per order.

## 11. Architecture Scenario: Moving a Media Archive to GCP

A company stores **180 TB** of raw video and images on a NAS, adding 100 GB daily. It wants data in Cloud Storage so Dataflow can extract metadata, BigQuery can power analytics, and a Cloud Run UI queries results.

**Proposed design:**

1. Build a manifest for the archive at checkpoint T0, lock a snapshot, and classify files.
2. Estimate usable Internet upload: 200 Mbps × 75% → ~111 days over WAN; evaluate Transfer Appliance TA300 and regional delivery availability.
3. Choose a bucket in the required residency region; configure IAM, security policies, and quotas; run a small test copy.
4. Copy the T0 snapshot to the Transfer Appliance; reconcile the manifest, finalize, and ship it back.
5. While ingestion runs, new data continues arriving: **100 GB/day** lands in a timestamped, cataloged delta zone to be transferred via an online tool such as Storage Transfer Service.
6. Once Google confirms ingestion, reconcile objects, logs, and checksums, sync the delta, and test the Dataflow / BigQuery pipeline.
7. Cut over the Cloud Run application to read target data using proper IAM; keep the NAS intact until data owners sign off.

**The hardest part is not plugging in cables:** you must ensure the T0 baseline and delta set neither drop files nor overwrite newer versions, while switching applications only once data is complete. If daily churn is massive or RPO must be very low, evaluate a dedicated online replication/streaming model for changes.

## 12. Key Takeaways Before Applying

- Transfer Appliance is a **large-scale data transfer** tool typically targeting **Cloud Storage**.
- Total TB is only one variable; measure effective throughput, file counts, and end-to-end cycle time.
- Offline mode eliminates WAN bottlenecks for massive initial loads; online mode works well when suitable bandwidth exists.
- Confirm country delivery availability, appliance models, usable capacity, and ordering rules early.
- Security spans **attestation, encryption, LAN segmentation, IAM, Cloud KMS, chain of custody, and data erasure**.
- Verify target data via **manifests, logs, checksums, and application tests** before deleting source data.
- A complete migration plan covers **incremental deltas, application cutover, costs, and recovery paths**.

## Official References

Capacity specs, procedures, and protocols are referenced from Google Cloud documentation. Re-verify when deploying as availability and procedures may be updated.

- [Transfer Appliance — Overview](https://docs.cloud.google.com/transfer-appliance/docs/4.0/overview)
- [Transfer Appliance — Specifications](https://docs.cloud.google.com/transfer-appliance/docs/4.0/specifications)
- [Transfer Appliance — High-level procedure](https://docs.cloud.google.com/transfer-appliance/docs/4.0/procedure-guide)
- [Transfer Appliance — Transfer data](https://docs.cloud.google.com/transfer-appliance/docs/4.0/transfer-data)
- [Transfer Appliance — Security and encryption](https://docs.cloud.google.com/transfer-appliance/docs/4.0/security-and-encryption)
- [Transfer Appliance — Access your data in Cloud Storage](https://docs.cloud.google.com/transfer-appliance/docs/4.0/access-data)
- [Storage Transfer Service — Data transfer options](https://docs.cloud.google.com/storage-transfer/docs/transfer-options)
